import re
from typing import Dict, List, Optional

import frappe
from frappe import _
from frappe import _lt

class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass

# ⚠️ DIQQAT — bu yerda ILGARI "ITEM_MAPPING" jadvali bor edi.
#
# U Excel'dagi nomni BOSHQA tovarga yo'naltirardi, masalan:
#     'Пицца гуштли катта' -> 'Пицца гуштли'   (katta pitsa kichik bo'lib tushardi)
#     'гошт 100 гр'        -> 'гошт 50 гр'     (izohi: "Closest match")
#     'Ок соус (собой)'    -> 'Ок соус (стол)'
# Holbuki bu nomlarning HAMMASI ERPNext'da alohida tovar sifatida mavjud edi.
# Natijada sotuv boshqa tovarga yozilib, ombor va tannarx ham buzilardi.
#
# Endi qoida qat'iy: Excel'dagi nom qanday bo'lsa, ERPNext'ga AYNAN o'sha
# tovar kiritiladi. Mos tovar topilmasa — import to'xtaydi va sabab xato
# jurnalida ko'rsatiladi. "Eng yaqin tovar"ni taxmin qilish TAQIQLANADI.


def normalize_item_name(name) -> str:
    """Nomni solishtirish uchun tozalaydi (nomni O'ZGARTIRMAYDI).

    Excel eksportida ko'zga ko'rinmas farqlar tez uchraydi: uzilmas bo'shliq
    (NBSP), qator oxiridagi probel, ketma-ket ikkita probel. Bular bir xil
    tovarni "topilmadi"ga chiqarardi. Bu yerda faqat o'sha ko'rinmas farqlar
    tekislanadi — harflar va so'zlar tegilmaydi.
    """
    if name is None:
        return ""
    text = str(name)
    for space in ("\u00a0", "\u202f", "\u2007", "\t"):
        text = text.replace(space, " ")
    return re.sub(r"\s+", " ", text).strip()


def _match_key(name) -> str:
    """Solishtirish kaliti — normalizatsiya + registrga befarqlik."""
    return normalize_item_name(name).casefold()


# Tovar topilmaslik sabablari — foydalanuvchiga tushunarli izoh bilan.
# _lt (lazy translate): matn modul yuklanganda emas, ishlatilganda
# tarjima qilinadi — aks holda jarayon qaysi tilda ko'tarilgan bo'lsa,
# o'sha til hamma uchun qotib qolardi.
PROBLEM_LABELS = {
    "not_found": _lt("ERPNext'da bunday tovar YO'Q"),
    "disabled": _lt("Tovar mavjud, lekin O'CHIRILGAN (Disabled)"),
    "template": _lt("Bu shablon tovar (variantli) — sotib bo'lmaydi"),
    "not_sales_item": _lt("Tovar sotuvga ruxsat etilmagan (Is Sales Item = 0)"),
    "ambiguous": _lt("Bir xil nomli bir nechta tovar bor — qaysi biri ekani noaniq"),
}


def build_item_index() -> Dict[str, List]:
    """Butun tovar ro'yxatini xotiraga oladi: {kalit -> [tovarlar]}.

    Kalit sifatida tovar kodi ham, tovar nomi ham olinadi. Bitta kalitga
    ikkita HAR XIL tovar tushsa — bu noaniqlik, import to'xtaydi (avval
    bunday holatda tasodifiy bittasi tanlanardi).
    """
    index = {}
    for row in frappe.get_all(
        "Item",
        fields=["name", "item_name", "disabled", "has_variants", "is_sales_item"],
    ):
        for key in {_match_key(row.name), _match_key(row.item_name)}:
            if not key:
                continue
            bucket = index.setdefault(key, [])
            if not any(x.name == row.name for x in bucket):
                bucket.append(row)
    return index


def suggest_similar(item_name: str, index: Dict[str, List], limit: int = 3) -> List[str]:
    """Topilmagan nomga eng yaqin MAVJUD tovar nomlarini qaytaradi.

    Bu — TAKLIF, avtomatik almashtirish EMAS. Ko'pincha farq bitta harfda
    bo'ladi (masalan "Пицца" / "Пизза") va operator qaysi nomni
    to'g'rilashni o'zi hal qiladi.
    """
    import difflib

    key = _match_key(item_name)
    if not key:
        return []

    close = difflib.get_close_matches(key, list(index.keys()), n=limit, cutoff=0.75)
    names = []
    for k in close:
        rows = index.get(k) or []
        if rows:
            label = rows[0].item_name or rows[0].name
            if rows[0].disabled:
                label += _(" (o'chirilgan)")
            names.append(label)
    return names


def resolve_item(item_name: str, index: Dict[str, List]) -> Dict:
    """Bitta Excel nomiga mos tovarni topadi — FAQAT aniq moslik bo'yicha.

    Qaytaradi: {"item_code": str|None, "problem": str|None, "detail": str}
    """
    key = _match_key(item_name)
    if not key:
        return {"item_code": None, "problem": "not_found", "detail": ""}

    matches = index.get(key) or []
    if not matches:
        return {"item_code": None, "problem": "not_found", "detail": ""}

    if len(matches) > 1:
        return {
            "item_code": None,
            "problem": "ambiguous",
            "detail": ", ".join(m.name for m in matches[:5]),
        }

    found = matches[0]
    if found.disabled:
        return {"item_code": None, "problem": "disabled", "detail": found.name}
    if found.has_variants:
        return {"item_code": None, "problem": "template", "detail": found.name}
    if not found.is_sales_item:
        return {"item_code": None, "problem": "not_sales_item", "detail": found.name}

    return {"item_code": found.name, "problem": None, "detail": ""}


def validate_import_prerequisites(
    company: str,
    source_warehouse: str,
    posting_date: str,
    customer: str = ""
) -> Dict:
    """Validate all prerequisites before import."""
    errors = []
    if not company: errors.append(_("Company tanlanmagan"))
    if not source_warehouse: errors.append(_("Ombor tanlanmagan"))
    if not posting_date: errors.append(_("Sana tanlanmagan"))
    if not customer: errors.append(_("Mijoz tanlanmagan"))

    if company and source_warehouse:
        wh_company = frappe.db.get_value("Warehouse", source_warehouse, "company")
        if wh_company and wh_company != company:
            errors.append(_("Warehouse '{0}' kompaniyaga tegishli emas: {1}").format(source_warehouse, company))

    if customer and not frappe.db.exists("Customer", customer):
        errors.append(_("'{0}' nomli mijoz topilmadi").format(customer))

    return {"success": len(errors) == 0, "message": "\n".join(errors), "errors": errors}

def validate_warehouse_company(warehouse: str, company: str):
    """Validate that warehouse belongs to the given company."""
    wh_company = frappe.db.get_value("Warehouse", warehouse, "company")
    if wh_company and wh_company != company:
        raise ValidationError(
            _("Warehouse '{0}' kompaniyaga tegishli emas: {1}").format(warehouse, company)
        )

def validate_items_exist(items: List[Dict]) -> Dict:
    """Har bir Excel qatorini ERPNext tovari bilan AYNAN solishtiradi.

    Qoida: nom bir xil bo'lsa — o'sha tovar; bo'lmasa — XATO. Taxmin yo'q,
    "o'xshash tovar" yo'q, qisman moslik yo'q. Bitta qator xato bo'lsa ham
    import bajarilmaydi — yarim-yorti import qilingandan ko'ra to'xtagani
    xavfsiz (buzuq sotuv keyin hisobotlarni ham buzadi).
    """
    index = build_item_index()

    valid_items = []
    errors = []
    # Xatolarni tovar nomi bo'yicha guruhlaymiz: 11 000 qatorli faylda
    # har bir qator uchun alohida satr yozilsa, jurnalni o'qib bo'lmaydi.
    grouped = {}

    for item in items:
        original_name = normalize_item_name(item.get("item_name"))
        row_num = item.get("row_num", 0)

        if not original_name:
            continue

        result = resolve_item(original_name, index)

        if result["item_code"]:
            item["item_code"] = result["item_code"]
            item["item_name"] = original_name
            item["found"] = True
            valid_items.append(item)
            continue

        item["found"] = False
        item["problem"] = result["problem"]

        label = str(PROBLEM_LABELS.get(result["problem"], result["problem"]))
        message = _("'{0}' — {1}").format(original_name, label)
        if result["detail"]:
            message += _(" (topilgani: {0})").format(result["detail"])

        errors.append({
            "row": row_num,
            "item_name": original_name,
            "problem": result["problem"],
            "error": message,
        })

        key = (original_name, result["problem"])
        entry = grouped.setdefault(key, {
            "item_name": original_name,
            "problem": result["problem"],
            "label": label,
            "detail": result["detail"],
            # Nom topilmasa — bazadagi eng yaqin nomlarni ko'rsatamiz
            "suggestions": (suggest_similar(original_name, index)
                            if result["problem"] == "not_found" else []),
            "rows": [],
            "qty": 0.0,
            "amount": 0.0,
        })
        entry["rows"].append(row_num)
        entry["qty"] += float(item.get("qty") or 0)
        entry["amount"] += float(item.get("qty") or 0) * float(item.get("rate") or 0)

    return {
        "valid_items": valid_items,
        "errors": errors,
        "problems": sorted(grouped.values(), key=lambda x: -x["amount"]),
        "success": len(errors) == 0,
    }


def format_item_problems(problems: List[Dict]) -> str:
    """Topilmagan tovarlar ro'yxatini o'qishga qulay matn qilib beradi.

    Shu matn hujjatning "Xato jurnali" (error_log) maydoniga tushadi —
    operator nimani tuzatishi kerakligini bir qarashda ko'rishi kerak,
    shuning uchun har tovar uchun: nomi, sababi, hajmi va (agar bazada
    o'xshash nom bo'lsa) TAKLIF ko'rsatiladi.
    """
    if not problems:
        return ""

    lines = []
    for i, p in enumerate(problems, 1):
        rows = p["rows"]
        shown = ", ".join(str(r) for r in rows[:8])
        if len(rows) > 8:
            shown += _(" va yana {0} ta").format(len(rows) - 8)

        lines.append(_("{0}) «{1}»").format(i, p["item_name"]))
        lines.append("   {0}".format(p["label"]))
        lines.append(_("   Excel qatori: {0}   |   {1:,.0f} dona   |   {2:,.0f} so'm").format(
            shown, p["qty"], p["amount"]))

        if p.get("detail") and p["problem"] != "not_found":
            lines.append(_("   ERPNext'dagi tovar: {0}").format(p["detail"]))

        # Eng muhimi — nima qilish kerakligi aynan shu tovar uchun
        suggestions = p.get("suggestions") or []
        if suggestions:
            lines.append(_("   ⚠️  Bazada O'XSHASH nom bor: {0}").format(
                "  /  ".join("«{0}»".format(x) for x in suggestions)))
            lines.append(_("   ➜ Ikkala nom bir xil bo'lishi kerak: yo ERPNext'dagi"))
            lines.append(_("     tovar nomini Excel'dagiga moslang, yo kassadagi nomni."))
        elif p["problem"] == "not_found":
            lines.append(_("   ➜ ERPNext'da AYNAN shu nom bilan yangi tovar yarating."))
        elif p["problem"] == "disabled":
            lines.append(_("   ➜ Tovar kartasini oching va 'Disabled' belgisini oling."))
        elif p["problem"] == "ambiguous":
            lines.append(_("   ➜ Takrorlangan tovarlardan bittasini o'chiring yoki nomini o'zgartiring."))
        else:
            lines.append(_("   ➜ Tovar kartasini tekshiring."))

        lines.append("")

    return "\n".join(lines).rstrip()


def check_duplicate_import(excel_hash: str, current_doc_name: str) -> Dict:
    """Check if this Excel file was already imported."""
    if not excel_hash:
        return {"is_duplicate": False, "existing_doc": None}
    
    existing = frappe.db.exists(
        "Jazira App Daily Sales Import",
        {
            "external_ref": excel_hash,
            "name": ["!=", current_doc_name],
            "status": "Processed"
        }
    )
    return {"is_duplicate": bool(existing), "existing_doc": existing}


def check_duplicate_dates(company: str, dates, current_doc_name: str) -> Dict:
    """Bu sanalar shu kompaniya uchun allaqachon import qilinganmi?

    check_duplicate_import() faqat Excel faylning hash'ini solishtiradi —
    fayl qayta eksport qilinsa yoki bitta katak o'zgartirilsa, hash boshqacha
    bo'lib, ayni kunni ikkinchi marta import qilish mumkin edi (amalda bir kun
    3 martagacha import qilingan holatlar bo'lgan).

    Bu tekshiruv esa sana darajasida ishlaydi: boshqa importga tegishli va
    hali SUBMIT holatida turgan Sales Invoice bor sanalarni bloklaydi.
    BEKOR QILINGAN (cancelled) SI to'sqinlik qilmaydi — ya'ni xato importni
    bekor qilib, o'sha kunni qayta yuklash bemalol mumkin.
    """
    dates = {str(d) for d in (dates or []) if d}
    if not dates or not company:
        return {"has_conflict": False, "conflicts": []}

    other_imports = frappe.get_all(
        "Jazira App Daily Sales Import",
        filters={"company": company, "name": ["!=", current_doc_name]},
        fields=["name", "sales_invoice"],
    )

    # Sales Invoice nomi -> uni yaratgan import hujjati
    si_owner = {}
    for imp in other_imports:
        if not imp.sales_invoice:
            continue
        for si_name in [s.strip() for s in imp.sales_invoice.split(",") if s.strip()]:
            si_owner.setdefault(si_name, imp.name)

    if not si_owner:
        return {"has_conflict": False, "conflicts": []}

    submitted = frappe.get_all(
        "Sales Invoice",
        filters={"name": ["in", list(si_owner.keys())], "docstatus": 1},
        fields=["name", "posting_date"],
    )

    conflicts = []
    seen_dates = set()
    for si in submitted:
        posting_date = str(si.posting_date)
        if posting_date in dates and posting_date not in seen_dates:
            seen_dates.add(posting_date)
            conflicts.append({
                "date": posting_date,
                "import_doc": si_owner[si.name],
                "sales_invoice": si.name,
            })

    conflicts.sort(key=lambda c: c["date"])
    return {"has_conflict": bool(conflicts), "conflicts": conflicts}
