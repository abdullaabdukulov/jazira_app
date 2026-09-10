import re
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, date

import frappe
from frappe import _

from jazira_app.jazira_app.utils.helpers import parse_numeric, get_file_path


@dataclass
class ExcelColumn:
    """Excel column configuration."""
    field_name: str
    headers: List[str]


class ExcelService:
    """
    Service for reading and parsing Excel files.

    Supports Uzbek POS report format with columns:
    - Nomi (mahsulot nomi)
    - Soni (miqdori)
    - Narxi (sotuv narxi)
    - Sana (ixtiyoriy - savdo sanasi)
    """

    # Column mapping configuration
    # Tartib MUHIM: har bir ro'yxatda ANIQROQ sarlavha oldinda turadi.
    # Aks holda "Filial nomi" ustuni "Tovar nomi"dan chapda bo'lsa, tovar
    # nomi noto'g'ri ustundan o'qilardi.
    COLUMNS = [
        ExcelColumn("item_name", ["tovar nomi", "mahsulot nomi", "наименование товара",
                                  "наименование", "mahsulot", "tovar", "nomi"]),
        ExcelColumn("qty", ["количество, шт.", "количество", "кол-во", "miqdori", "miqdor",
                            "soni"]),
        ExcelColumn("rate", ["sotuv narxi", "цена продажи", "цена, шт.", "narxi", "narx",
                             "цена"]),
        ExcelColumn("datetime", ["дата продажи", "savdo sanasi", "дата", "sana",
                                 "datetime", "date"]),
    ]

    # Narx ustunini tanlashda BU so'zlar uchrasa — bu sotuv narxi emas.
    # Xarid narxi ustuni tanlansa, butun sotuv tannarx bo'yicha yozilardi.
    RATE_BLACKLIST = ["приход", "покупк", "закуп", "себестоимост", "xarid", "tannarx"]

    # Rows to skip (summary rows)
    SKIP_KEYWORDS = ["jami", "итого", "всего", "total", "сумма", "umumiy"]
    
    def __init__(self):
        self._ensure_openpyxl()
    
    def _ensure_openpyxl(self):
        """Ensure openpyxl is installed."""
        try:
            import openpyxl  # noqa
        except ImportError:
            frappe.throw(_("openpyxl not installed. Run: pip install openpyxl"))
    
    def read_sales_report(self, file_url: str) -> Dict:
        """
        Read POS sales report from Excel file.

        Args:
            file_url: Frappe file URL

        Returns:
            Dict with keys:
                - items: List of dicts with keys: item_name, qty, rate, row_num, date
                - posting_date: str (YYYY-MM-DD) from first row as fallback

        Raises:
            frappe.ValidationError: If file cannot be read or required columns missing
        """
        from openpyxl import load_workbook

        file_path = get_file_path(file_url)
        if not file_path:
            frappe.throw(_("Excel fayl topilmadi: {0}").format(file_url))

        wb = load_workbook(file_path, data_only=True)
        ws = wb.active

        try:
            # Find header row and column indices
            column_indices = self._find_columns(ws)
            header_row = column_indices.get("_header_row", 1)

            # Validate required columns
            self._validate_required_columns(column_indices)

            # Read data rows
            items, skipped = self._read_data_rows(ws, column_indices, header_row)

            # Extract first valid date as fallback/summary date
            excel_date = None
            for item in items:
                if item.get("date"):
                    excel_date = item["date"]
                    break

            return {
                "items": items,
                "posting_date": excel_date,
                # Tashlab yuborilgan qatorlar OSHKOR qilinadi: avval ular
                # jimgina yo'qolardi va Excel jamisi bilan ERPNext jamisi
                # nega farq qilgani noma'lum bo'lib qolardi.
                "skipped": skipped,
                "has_rate_column": "rate" in column_indices,
                "columns": {k: v for k, v in column_indices.items() if not k.startswith("_")},
            }

        finally:
            wb.close()
    
    def _find_columns(self, worksheet) -> Dict[str, int]:
        """Sarlavha qatorini topib, ustun raqamlarini aniqlaydi.

        Avval HAQIQIY sarlavha qatori topiladi (ichida ham tovar nomi, ham
        miqdor ustuni bor qator), keyin barcha ustunlar FAQAT o'sha qatordan
        olinadi. Avval bunday emasdi: yuqoridagi "Дата: 04.07.2026" kabi
        sarlavha ustidagi qatordan ham ustun olinib qolardi va sana butunlay
        boshqa ustundan o'qilardi — natijada fakturalar noto'g'ri kunga
        tushish xavfi bor edi.
        """
        header_row, cells = self._locate_header_row(worksheet)
        if not header_row:
            return {}

        column_indices = {"_header_row": header_row}

        for exact_pass in (True, False):
            for column in self.COLUMNS:
                if column.field_name in column_indices:
                    continue
                for header in column.headers:
                    hits = [c for c, val in cells
                            if (val == header if exact_pass else header in val)]
                    if column.field_name == "rate":
                        hits = [c for c in hits if not self._is_purchase_price(c, cells)]
                    if len(hits) == 1:
                        column_indices[column.field_name] = hits[0]
                        break
                    if len(hits) > 1 and exact_pass:
                        # Bir xil aniq sarlavha ikki marta — qaysi biri
                        # ekanini taxmin qilmaymiz.
                        frappe.throw(_(
                            "Excel'da '{0}' sarlavhasi bir necha ustunda uchradi — "
                            "qaysi biri kerakligi noaniq. Faylni tekshiring."
                        ).format(header))

        return column_indices

    def _locate_header_row(self, worksheet):
        """Ham tovar nomi, ham miqdor sarlavhasi bor qatorni topadi."""
        for row_num, row in enumerate(worksheet.iter_rows(min_row=1, max_row=15), start=1):
            cells = [(c, str(cell.value).lower().strip())
                     for c, cell in enumerate(row, start=1) if cell.value is not None]
            if not cells:
                continue
            has_name = any(h in val for _c, val in cells
                           for h in self.COLUMNS[0].headers)
            has_qty = any(h in val for _c, val in cells
                          for h in self.COLUMNS[1].headers)
            if has_name and has_qty:
                return row_num, cells
        return None, []

    def _is_purchase_price(self, col, cells):
        """Ustun sarlavhasi xarid/tannarx narxini bildiradimi?"""
        val = next((v for c, v in cells if c == col), "")
        return any(bad in val for bad in self.RATE_BLACKLIST)

    def _validate_required_columns(self, column_indices: Dict):
        """Validate that required columns are found."""
        if not column_indices:
            frappe.throw(_(
                "Excel faylida sarlavha qatori topilmadi — 'Nomi' va 'Soni' "
                "ustunlari bitta qatorda bo'lishi kerak."))

        if "item_name" not in column_indices:
            frappe.throw(_("Excel faylida 'Nomi' ustuni topilmadi"))

        if "qty" not in column_indices:
            frappe.throw(_("Excel faylida 'Soni' ustuni topilmadi"))
    
    def _read_data_rows(
        self,
        worksheet,
        column_indices: Dict[str, int],
        header_row: int
    ) -> tuple:
        """Ma'lumot qatorlarini o'qiydi.

        Qaytaradi: (items, skipped). O'qilmagan har bir qator `skipped`
        ro'yxatiga sababi bilan tushadi — hech narsa "sassiz" yo'qolmaydi.
        """
        items = []
        skipped = []

        item_name_col = column_indices["item_name"] - 1
        qty_col = column_indices["qty"] - 1
        rate_col = column_indices.get("rate", 0) - 1 if "rate" in column_indices else None
        dt_col = column_indices.get("datetime", 0) - 1 if "datetime" in column_indices else None

        for row_num, row in enumerate(
            worksheet.iter_rows(min_row=header_row + 1),
            start=header_row + 1
        ):
            item_name = self._get_cell_value(row, item_name_col)
            qty, qty_ok = self._get_cell_number(row, qty_col)

            # Butunlay bo'sh qator — hisobotga ham kerak emas
            if not item_name:
                if qty:
                    skipped.append({"row": row_num, "item_name": "",
                                    "reason": "no_name", "qty": qty})
                continue

            if self._is_summary_row(item_name):
                skipped.append({"row": row_num, "item_name": item_name,
                                "reason": "summary", "qty": qty})
                continue

            # Miqdor o'qilmadi ("2 dona" kabi) — bu 0 emas, NOMA'LUM.
            # Avval ikkalasi ham 0 bo'lib, haqiqiy sotuv indamay yo'qolardi.
            if not qty_ok:
                skipped.append({"row": row_num, "item_name": item_name,
                                "reason": "bad_qty",
                                "raw": self._get_cell_value(row, qty_col)})
                continue

            if qty == 0:
                skipped.append({"row": row_num, "item_name": item_name,
                                "reason": "zero_qty", "qty": 0})
                continue
            if qty < 0:
                # Manfiy miqdor — qaytarilgan tovar. Avval u ham jimgina
                # tashlanardi, ya'ni qaytarilgan mol sotuvdan ayrilmasdan
                # qolardi. Endi bu holat oshkor xato sifatida chiqadi.
                skipped.append({"row": row_num, "item_name": item_name,
                                "reason": "negative_qty", "qty": qty})
                continue

            rate = 0.0
            if rate_col is not None and rate_col >= 0:
                rate, rate_ok = self._get_cell_number(row, rate_col)
                if not rate_ok:
                    skipped.append({"row": row_num, "item_name": item_name,
                                    "reason": "bad_rate",
                                    "raw": self._get_cell_value(row, rate_col)})
                    continue

            item_date = None
            if dt_col is not None and dt_col >= 0:
                item_date = self._parse_cell_date(row[dt_col].value)

            items.append({
                "item_name": item_name,
                "qty": qty,
                "rate": rate,
                "row_num": row_num,
                "date": item_date
            })

        return items, skipped

    def _get_cell_number(self, row, col_index) -> tuple:
        """Katakdan raqam oladi: (qiymat, o'qildimi).

        XOM qiymat bilan ishlaydi. Avval har bir katak avval matnga
        aylantirilardi va "0.500" kabi qiymat 500 bo'lib ketardi (nuqta
        minglik ajratgich deb hisoblangani uchun).
        """
        if col_index is None or col_index < 0 or col_index >= len(row):
            return 0.0, True

        raw = row[col_index].value
        if raw is None:
            return 0.0, True
        if isinstance(raw, bool):
            return 0.0, False
        if isinstance(raw, (int, float)):
            return float(raw), True

        text = str(raw).strip()
        if not text:
            return 0.0, True

        value = parse_numeric(text)
        # parse_numeric o'qiy olmasa ham 0.0 qaytaradi — haqiqiy noldan
        # ajratish uchun matnning o'zini tekshiramiz.
        ok = value != 0.0 or re.fullmatch(r"[-+0\s.,]+", text) is not None
        return value, ok

    def _parse_cell_date(self, cell_value) -> Optional[str]:
        """Parse a single cell value into YYYY-MM-DD string."""
        if cell_value is None:
            return None

        # Handle datetime/date objects from Excel
        if isinstance(cell_value, datetime):
            return cell_value.strftime("%Y-%m-%d")
        if isinstance(cell_value, date):
            return cell_value.strftime("%Y-%m-%d")

        # Handle string dates
        cell_str = str(cell_value).strip()
        if not cell_str:
            return None

        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M:%S"):
            try:
                return datetime.strptime(cell_str, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue

        return None

    def _get_cell_value(self, row, col_index: int) -> Optional[str]:
        """Safely get cell value."""
        if col_index < 0 or col_index >= len(row):
            return None
        
        value = row[col_index].value
        if value is None:
            return None
        
        return str(value).strip()
    
    def _is_summary_row(self, item_name: str) -> bool:
        """Qator "Jami/Итого" kabi yakuniy qatormi?

        Avval oddiy ichki qidiruv edi: nomi ichida "сумма" yoki "total"
        uchraydigan HAQIQIY tovar ham yakuniy qator deb tashlab ketilardi.
        Endi faqat butun so'z sifatida (yoki qator shu so'zdan boshlansa)
        hisobga olinadi.
        """
        # Faqat BUTUN so'z sifatida. Avval "startswith" ham bor edi va
        # "Jamiyat pitsa" kabi haqiqiy taom ham yakuniy qator deb tashlab
        # ketilardi.
        words = set(re.split(r"[^\w]+", item_name.lower().strip()))
        return any(kw in words for kw in self.SKIP_KEYWORDS)


excel_service = ExcelService()
