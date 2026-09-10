from typing import Dict, List, Any
from collections import defaultdict
import copy

import frappe
from frappe import _
from frappe import _lt
from frappe.utils import nowdate

from jazira_app.jazira_app.utils import (
    calculate_file_hash,
    validate_import_prerequisites,
    validate_items_exist,
    format_item_problems,
    check_duplicate_import,
    check_duplicate_dates
)
from jazira_app.jazira_app.services import (
    excel_service,
    bom_service,
    stock_service,
    invoice_service,
    StockEntryConfig,
    InvoiceConfig
)


@frappe.whitelist()
def get_default_warehouse(company: str) -> Dict:
    """Get default warehouse for a company."""
    if not company:
        return {"source_warehouse": None}
    
    warehouse = frappe.db.get_value(
        "Warehouse",
        {"company": company, "is_group": 0, "warehouse_type": "Stores"},
        "name"
    )
    
    if not warehouse:
        warehouse = frappe.db.get_value(
            "Warehouse",
            {"company": company, "is_group": 0},
            "name"
        )
    
    return {"source_warehouse": warehouse}


# =============================================================================
# TEKSHIRUV BOSQICHI
# =============================================================================
#
# Qoida: HUJJAT YARATISHDAN OLDIN hamma narsa tekshiriladi. Bittagina xato
# bo'lsa — hech qanday Sales Invoice yoki Stock Entry yaratilmaydi.
#
# Avval bunday emas edi: tekshiruv yuzaki bo'lib, import sanama-sana
# yaratib ketaverardi va 5-kunda xato chiqsa, oldingi 4 kunning hujjatlari
# tizimda submit holatda qolib ketardi.

class PreflightError(Exception):
    """Tekshiruv bosqichida to'xtatilgan import.

    Oddiy Exception'dan farqi: xatoning TO'LIQ hisobotini ham olib yuradi.
    Tashqi `except` bloki error_log'ga faqat qisqa xabarni yozib qo'ysa,
    operator "batafsil sabab jurnalda" degan yozuvni ko'rib, jurnalda esa
    o'sha qisqa xabarni topardi.
    """

    def __init__(self, message, report=""):
        super().__init__(message)
        self.report = report


# _lt — "lazy" tarjima: matn modul yuklanganda emas, ishlatilganda
# tarjima qilinadi. Oddiy _() ishlatilsa, jarayon qaysi tilda ko'tarilgan
# bo'lsa, hamma foydalanuvchi uchun o'sha til qotib qolardi.
SKIP_REASON_LABELS = {
    "summary": _lt("yakuniy/jami qatori"),
    "zero_qty": _lt("miqdori 0"),
    "no_name": _lt("tovar nomi bo'sh"),
    "negative_qty": _lt("MANFIY miqdor (qaytarilgan tovar)"),
    "bad_qty": _lt("miqdorni o'qib bo'lmadi"),
    "bad_rate": _lt("narxni o'qib bo'lmadi"),
}

# Bu sabablar importni TO'XTATADI — ular ma'lumot yo'qolishini bildiradi
BLOCKING_SKIP_REASONS = ("negative_qty", "bad_qty", "bad_rate")


def run_preflight_checks(doc) -> Dict:
    """Importdan oldingi to'liq tekshiruv.

    Excel'dagi har bir tovar ERPNext'da AYNAN shu nom bilan bormi, faolmi,
    sotiladimi — hammasi shu yerda tekshiriladi. Shuningdek: narx ustuni,
    tashlab yuborilgan qatorlar, dublikat sana va retsept (BOM) butunligi.

    Qaytaradi: success, errors (bloklovchi), warnings (ogohlantirish),
    row_errors (UI ro'yxati uchun), report (error_log matni), valid_items,
    dates, excel_hash.
    """
    errors = []
    warnings = []
    row_errors = []
    report_blocks = []

    empty = {
        "success": False, "errors": errors, "warnings": warnings,
        "row_errors": row_errors, "report": "", "valid_items": [],
        "dates": [], "excel_hash": "",
    }

    # 1) Hujjat rekvizitlari
    if not doc.excel_file:
        errors.append(_("Excel fayl yuklanmagan"))
        empty["report"] = "\n".join(errors)
        return empty

    prereq = validate_import_prerequisites(
        doc.company, doc.source_warehouse, str(doc.posting_date), doc.customer or ""
    )
    if not prereq["success"]:
        errors.extend(prereq["errors"])

    # 2) Excel o'qish
    try:
        excel_data = excel_service.read_sales_report(doc.excel_file)
    except Exception as e:
        errors.append(_("Excel o'qilmadi: {0}").format(str(e)))
        empty["report"] = "\n".join(errors)
        return empty

    items = excel_data["items"]
    skipped = excel_data.get("skipped") or []

    if not items:
        errors.append(_("Excel faylda sotuv qatori topilmadi"))

    # 3) Narx ustuni — bo'lmasa hamma narsa 0 so'mga tushib ketardi
    if not excel_data.get("has_rate_column"):
        errors.append(_(
            "Excel'da narx ustuni ('Narxi' / 'Цена продажи') topilmadi — "
            "bu holda hamma sotuv 0 so'mga yozilib ketardi."
        ))

    # 4) O'qilmagan qatorlar — oshkor qilinadi
    by_reason = defaultdict(list)
    for sk in skipped:
        by_reason[sk["reason"]].append(sk)

    for reason, rows in by_reason.items():
        label = str(SKIP_REASON_LABELS.get(reason, reason))
        text = _("{0} ta qator o'qilmadi — {1}").format(len(rows), label)
        if reason in BLOCKING_SKIP_REASONS:
            # Bu qatorlarda HAQIQIY sotuv bor, lekin o'qib bo'lmadi yoki
            # qaytarilgan tovar. Jimgina tashlansa — sotuv noto'g'ri
            # chiqadi, shuning uchun import to'xtaydi.
            sample = ", ".join(
                _("{0}-qator: {1} [{2}]").format(
                    r["row"], r["item_name"], r.get("raw", r.get("qty")))
                for r in rows[:5])
            errors.append(text + ". " + _("Qo'lda ko'rib chiqing: {0}").format(sample))
        else:
            warnings.append(text)

    # 5) TOVARLAR — asosiy tekshiruv (aynan moslik)
    validation = validate_items_exist(items)
    valid_items = validation["valid_items"]
    if validation["errors"]:
        row_errors.extend(validation["errors"])
        problem_text = format_item_problems(validation["problems"])
        report_blocks.append(problem_text)
        errors.append(_("{0} ta tovar ERPNext bilan mos kelmadi (quyida ro'yxati)").format(
            len(validation["problems"])))

    # 6) Narxi 0 bo'lgan qatorlar — ogohlantirish
    zero_rate = [i for i in valid_items if not (i.get("rate") or 0)]
    if zero_rate:
        warnings.append(_("{0} ta qatorda narx 0 — sotuv summasiz yoziladi").format(len(zero_rate)))

    # 7) Retsept (BOM) butunligi — yarim yo'lda to'xtab qolmasin
    if valid_items:
        errors.extend(_check_bom_integrity(valid_items, doc.company))

    # 8) Dublikat fayl va dublikat sana
    excel_hash = calculate_file_hash(doc.excel_file)
    duplicate = check_duplicate_import(excel_hash, doc.name)
    if duplicate["is_duplicate"]:
        errors.append(_("Bu Excel avval import qilingan: {0}").format(duplicate["existing_doc"]))

    fallback_date = str(doc.posting_date)
    dates = sorted({(i.get("date") or fallback_date) for i in valid_items})
    date_check = check_duplicate_dates(doc.company, dates, doc.name)
    for c in date_check["conflicts"]:
        errors.append(_("{0} sanasi allaqachon import qilingan ({1} → {2}). Avval o'sha importni bekor qiling.").format(
            c["date"], c["import_doc"], c["sales_invoice"]))

    # ── Yakuniy hisobot matni ──
    #
    # Tuzilishi ataylab sodda: eng tepada NIMA QILISH kerakligi, keyin
    # tafsilot. Avval xatolar ro'yxati ikki marta (umumiy + batafsil)
    # takrorlanib, o'qish qiyin bo'lardi.
    report = ""
    if errors:
        head = [
            "❌ " + _("IMPORT BAJARILMADI"),
            "=" * 60,
            "",
        ]
        if report_blocks:
            head.append(_("Quyidagi tovarlar ERPNext bilan mos kelmadi."))
            head.append(_("Ular to'g'rilanmaguncha hech qanday hujjat yaratilmaydi."))
            head.append("")
            head.append("-" * 60)
            head.append("")
            head.append("\n\n".join(report_blocks))
            head.append("")

        # Tovarlardan boshqa xatolar (sana dublikati, narx ustuni va h.k.)
        other = [e for e in errors if _("mos kelmadi") not in e]
        if other:
            head.append("-" * 60)
            head.append(_("Boshqa xatolar:"))
            head.extend("  • {0}".format(e) for e in other)
            head.append("")

        head.append("=" * 60)
        head.append(_("Tuzatgach, 'Import' tugmasini qayta bosing."))
        report = "\n".join(head)

    return {
        "success": not errors,
        "errors": errors,
        "warnings": warnings,
        "row_errors": row_errors,
        "report": report,
        "valid_items": valid_items,
        "dates": dates,
        "excel_hash": excel_hash,
        "skipped": skipped,
        "columns": excel_data.get("columns") or {},
    }


def _check_bom_integrity(valid_items: List[Dict], company: str) -> List[str]:
    """Retseptli tovarlarning xomashyosi joyidami?

    Xomashyo o'chirilgan bo'lsa yoki retsept bo'sh bo'lsa, Stock Entry
    import o'rtasida yiqilardi (yoki jimgina yaratilmasdan qolardi) —
    tovar sotilgan, lekin xomashyo hisobdan chiqmagan holat kelib chiqardi.
    """
    problems = []
    checked = set()
    needed = {}

    for item in valid_items:
        code = item.get("item_code")
        if not code or code in checked:
            continue
        checked.add(code)

        bom = bom_service.get_default_bom(code)
        if not bom:
            continue  # retseptsiz tovar — to'g'ridan-to'g'ri sotiladi

        try:
            materials = bom_service.get_raw_materials(bom, 1, company)
        except Exception as e:
            problems.append(_("'{0}' retsepti ({1}) ochilmadi: {2}").format(code, bom, str(e)))
            continue

        if not materials:
            problems.append(_("'{0}' retsepti ({1}) bo'sh — xomashyo hisobdan chiqmaydi").format(code, bom))
            continue

        needed[code] = [m.item_code for m in materials]

    # Butun xomashyo ro'yxati BITTA so'rovda tekshiriladi (avval har
    # retsept uchun alohida so'rov ketardi — 112 ta retseptda ~2 sekund).
    all_codes = {c for codes in needed.values() for c in codes}
    disabled = set(frappe.get_all(
        "Item", filters={"name": ["in", list(all_codes)], "disabled": 1}, pluck="name")
    ) if all_codes else set()

    for code, codes in needed.items():
        bad = [c for c in codes if c in disabled]
        if bad:
            problems.append(_("'{0}' retseptidagi xomashyo o'chirilgan: {1}").format(
                code, ", ".join(bad)))

    return problems


@frappe.whitelist()
def get_preview_data(doc_name: str) -> Dict:
    """Get preview of Excel data before processing."""
    doc = frappe.get_doc("Jazira App Daily Sales Import", doc_name)
    
    if not doc.excel_file:
        return {"success": False, "message": _("Excel fayl yuklanmagan")}
    
    try:
        excel_data = excel_service.read_sales_report(doc.excel_file)
        items = excel_data["items"]
        skipped = excel_data.get("skipped") or []

        validation = validate_items_exist(items)
        valid_items = validation["valid_items"]

        # Retseptlar BITTA so'rovda olinadi. Avval har QATOR uchun alohida
        # so'rov ketardi — 11 000 qatorli faylda ~18 sekund kutish.
        codes = {i["item_code"] for i in valid_items if i.get("item_code")}
        boms = {}
        if codes:
            for row in frappe.get_all(
                "BOM",
                filters={"item": ["in", list(codes)], "is_default": 1,
                         "is_active": 1, "docstatus": 1},
                fields=["name", "item"],
            ):
                boms.setdefault(row.item, row.name)

        for item in items:
            code = item.get("item_code")
            bom = boms.get(code) if code else None
            if code:
                item["has_bom"] = bool(bom)
                item["bom"] = bom
                item["type"] = "MANUFACTURE" if bom else "DIRECT SALE"
            else:
                item["has_bom"] = False
                item["type"] = "NOT FOUND"

        found_items = [i for i in items if i.get("found")]
        summary = {
            "total_items": len(items),
            "found": len(found_items),
            "not_found": len(items) - len(found_items),
            "with_bom": len([i for i in items if i.get("has_bom")]),
            "without_bom": len([i for i in found_items if not i.get("has_bom")]),
            "total_qty": sum(i.get("qty", 0) for i in items),
            "total_amount": sum(i.get("qty", 0) * i.get("rate", 0) for i in items),
            # O'qilmagan qatorlar ham ko'rinsin — aks holda preview jamisi
            # bilan import jamisi nega farq qilgani tushunarsiz bo'lardi.
            "skipped": len(skipped),
        }

        return {
            "success": True, 
            "items": items, 
            "summary": summary, 
            "excel_posting_date": excel_data["posting_date"]
        }
        
    except Exception as e:
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def validate_excel_items(doc_name: str) -> Dict:
    """"Tekshirish" tugmasi — importni ishga tushirmasdan oldingi nazorat.

    Import bosilganda ishlaydigan AYNAN o'sha tekshiruvni bajaradi, shuning
    uchun bu yerda "toza" degan javob importda ham toza degani.
    """
    doc = frappe.get_doc("Jazira App Daily Sales Import", doc_name)

    try:
        pre = run_preflight_checks(doc)
    except Exception as e:
        return {"success": False, "message": str(e), "errors": [], "items": []}

    # UI ro'yxati uchun: avval umumiy xatolar, keyin tovar bo'yicha qatorlar
    errors = [{"row": 0, "item_name": "", "error": e} for e in pre["errors"]]
    errors.extend(pre["row_errors"])

    totals = invoice_service.calculate_totals(pre["valid_items"])

    if pre["success"]:
        message = _("✅ Tekshiruv toza: {0} ta qator, {1:,.0f} so'm. Import qilsa bo'ladi.").format(
            len(pre["valid_items"]), totals["total_amount"])
    else:
        message = _("❌ {0} ta muammo topildi — import bajarilmaydi").format(len(errors))

    return {
        "success": pre["success"],
        "message": message,
        "errors": errors,
        "warnings": pre["warnings"],
        "items": pre["valid_items"],
        "total_qty": totals["total_qty"],
        "total_amount": totals["total_amount"],
    }


@frappe.whitelist()
def process_import(doc_name: str, background: bool = False) -> Dict:
    """Process the import — always runs in background to prevent HTTP timeout."""
    doc = frappe.get_doc("Jazira App Daily Sales Import", doc_name)

    if doc.status == "Processed":
        return {"success": False, "message": _("Bu import allaqachon bajarilgan")}

    if doc.status == "Processing":
        return {"success": False, "message": _("Import hozir jarayonda")}

    # Quick pre-validation (lightweight — no heavy processing)
    if not doc.excel_file:
        return {"success": False, "message": _("Excel fayl yuklanmagan")}

    validation = validate_import_prerequisites(
        doc.company, doc.source_warehouse, str(doc.posting_date), doc.customer or ""
    )
    if not validation["success"]:
        return {"success": False, "message": validation["message"]}

    # Check duplicate before enqueueing
    excel_hash = calculate_file_hash(doc.excel_file)
    duplicate = check_duplicate_import(excel_hash, doc_name)
    if duplicate["is_duplicate"]:
        return {
            "success": False,
            "message": _("Bu Excel avval import qilingan: {0}").format(duplicate["existing_doc"])
        }

    # Mark as Processing before enqueueing to prevent double-clicks
    doc.db_set("status", "Processing")
    doc.db_set("error_log", "")
    doc.db_set("import_log", "")
    frappe.db.commit()

    # Always enqueue to background
    frappe.enqueue(
        _process_import_job,
        queue="long",
        timeout=3600,
        doc_name=doc_name
    )
    return {"success": True, "message": _("Import fonada boshlandi. Sahifani yangilab turing.")}


def _process_import_job(doc_name: str):
    """Background job wrapper."""
    try:
        result = _process_import_sync(doc_name)
        event = "restaurant_import_success" if result["success"] else "restaurant_import_failed"
        frappe.publish_realtime(
            event,
            {"doc_name": doc_name, "result": result},
            doctype="Jazira App Daily Sales Import",
            docname=doc_name
        )
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Import Error: {doc_name}\n{str(e)}", "Daily Sales Import")
        try:
            doc = frappe.get_doc("Jazira App Daily Sales Import", doc_name)
            doc.db_set("status", "Failed")
            doc.db_set("error_log", getattr(e, "report", "") or str(e))
            frappe.db.commit()
        except Exception:
            pass
        frappe.publish_realtime(
            "restaurant_import_failed",
            {"doc_name": doc_name, "result": {"success": False, "message": str(e)}},
            doctype="Jazira App Daily Sales Import",
            docname=doc_name
        )


def _process_import_sync(doc_name: str) -> Dict:
    """Synchronous import processing with multi-date support."""
    doc = frappe.get_doc("Jazira App Daily Sales Import", doc_name)
    
    log_lines = []
    def log(msg, publish=True):
        log_lines.append(msg)
        current_log = "\n".join(log_lines)
        frappe.db.set_value("Jazira App Daily Sales Import", doc_name, "import_log", current_log, update_modified=False)
        if publish:
            frappe.publish_realtime(
                "restaurant_import_log",
                {"doc_name": doc_name, "msg": msg, "full_log": current_log},
                doctype="Jazira App Daily Sales Import",
                docname=doc_name
            )
    
    if doc.status == "Processed":
        return {"success": False, "message": _("Bu import allaqachon bajarilgan")}
    
    # Status already set to Processing by process_import(), but ensure it
    if doc.status != "Processing":
        doc.db_set("status", "Processing")
        doc.db_set("error_log", "")
        frappe.db.commit()
    
    log("=" * 50)
    log(f"IMPORT BOSHLANDI: {nowdate()}")
    log(f"Company: {doc.company}")
    log(f"Warehouse: {doc.source_warehouse}")
    log("=" * 50)
    
    try:
        # ═══════════════ 1-BOSQICH: TO'LIQ TEKSHIRUV ═══════════════
        # Bu bosqichda HECH QANDAY hujjat yaratilmaydi. Xato topilsa,
        # import shu yerda to'xtaydi — tizimga yarim-yorti ma'lumot
        # tushmasligi kafolatlanadi.
        log("\n📋 1-BOSQICH: TO'LIQ TEKSHIRUV (hujjat yaratilmaydi)")
        pre = run_preflight_checks(doc)

        cols = pre.get("columns") or {}
        if cols:
            log("   📑 Aniqlangan ustunlar: " + ", ".join(f"{k}→{v}" for k, v in sorted(cols.items())))
        log(f"   📊 O'qilgan sotuv qatori: {len(pre['valid_items'])}")

        for w in pre["warnings"]:
            log(f"   ⚠️  {w}")

        if not pre["success"]:
            # Batafsil hisobot "Xato jurnali" maydoniga tushadi — bu yerda
            # takrorlamaymiz, aks holda bitta xato ikki marta chiqib,
            # jurnalni o'qish qiyinlashardi.
            for e in pre["errors"]:
                log(f"   ❌ {e}")
            log("")
            log("   " + _("Batafsil ro'yxat va nima qilish kerakligi — "
                          "pastdagi 'Xato jurnali' bo'limida."))
            raise PreflightError(
                _("Tekshiruvda {0} ta xato topildi — import bajarilmadi. "
                  "Batafsil sabab 'Xato jurnali' bo'limida.").format(len(pre["errors"])),
                report=pre["report"] or "\n".join(pre["errors"]),
            )

        valid_items = pre["valid_items"]
        excel_hash = pre["excel_hash"]
        sorted_dates = pre["dates"]
        log(f"   ✅ Barcha {len(valid_items)} ta qator tekshiruvdan o'tdi")
        log(f"   📅 Jami {len(sorted_dates)} xil sana aniqlandi")

        # Sana bo'yicha guruhlash
        items_by_date = defaultdict(list)
        fallback_date = str(doc.posting_date)
        for item in valid_items:
            items_by_date[item.get("date") or fallback_date].append(item)

        # ═══════════════ 2-BOSQICH: HUJJAT YARATISH ═══════════════
        log("\n🏗️  2-BOSQICH: HUJJAT YARATISH")

        all_se_names = []
        all_si_names = []
        total_amount = 0
        
        # ── Davom ettirish (resume) ────────────────────────────────────
        # Import har sanani alohida commit qiladi. 5-kunda xato bo'lsa,
        # oldingi kunlar allaqachon yaratilgan — ularni qayta yaratmaymiz.
        #
        # LEKIN: agar operator Excel'ni TUZATIB qayta yuklasa, tuzatilgan
        # kunlar "allaqachon bajarilgan" deb o'tkazib yuborilar va import
        # "muvaffaqiyatli" deb tugardi — ya'ni tuzatish jimgina yo'qolardi.
        # Shuning uchun fayl o'zgargan bo'lsa, davom ettirish TAQIQLANADI.
        already_done_dates = set()
        if doc.sales_invoice:
            existing_si_names = [s.strip() for s in doc.sales_invoice.split(",") if s.strip()]

            if doc.external_ref and doc.external_ref != excel_hash:
                raise PreflightError(
                    _("Excel fayl o'zgargan, lekin bu importda allaqachon "
                      "hujjatlar yaratilgan. Avval 'Bekor qilish' tugmasi bilan "
                      "importni bekor qiling, keyin yangi faylni yuklang."),
                    report=_(
                        "IMPORT DAVOM ETTIRILMADI\n"
                        "{0}\n\n"
                        "Bu hujjat oldin {1} ta Sales Invoice yaratgan, lekin Excel "
                        "fayl o'shandan beri o'zgargan.\n\n"
                        "Nima qilish kerak:\n"
                        "  1. 'Bekor qilish' tugmasini bosing — yaratilgan hujjatlar "
                        "bekor qilinadi;\n"
                        "  2. Keyin importni qaytadan ishga tushiring."
                    ).format("=" * 64, len(existing_si_names)),
                )

            all_si_names.extend(existing_si_names)
            # Faqat HAQIQATDA kuchda turgan (submit qilingan) fakturalar
            # sanani "bajarilgan" deb belgilaydi. Avval docstatus
            # tekshirilmasdi: qo'lda bekor qilingan faktura ham sanani
            # to'sib qo'yardi va o'sha kun umuman import qilinmay qolardi.
            for si_name in existing_si_names:
                si = frappe.db.get_value(
                    "Sales Invoice", si_name, ["posting_date", "docstatus"], as_dict=True)
                if si and si.docstatus == 1:
                    already_done_dates.add(str(si.posting_date))

        if doc.stock_entry:
            existing_se_names = [s.strip() for s in doc.stock_entry.split(",") if s.strip()]
            all_se_names.extend(existing_se_names)

        if already_done_dates:
            log(f"   ♻️ Davom ettirish: {len(already_done_dates)} ta sana oldin bajarilgan, o'tkazib yuboriladi")
        
        # Process each date
        for idx, d in enumerate(sorted_dates, 1):
            date_items = items_by_date[d]
            
            # Skip already processed dates (resume mode)
            if d in already_done_dates:
                log(f"\n--- [{idx}/{len(sorted_dates)}] SANA: {d} — ⏭️ oldin bajarilgan, skip ---")
                continue
            
            log(f"\n--- [{idx}/{len(sorted_dates)}] SANA: {d} ({len(date_items)} ta item) ---")

            # Sana dublikati YARATISHDAN OLDIN qayta tekshiriladi.
            # Tekshiruv bosqichi bilan yaratish orasida boshqa import shu
            # kunni yozib ulgurishi mumkin (ilgari bir kun 3 marta import
            # qilingan holatlar bo'lgan) — bu oyna shu bilan yopiladi.
            recheck = check_duplicate_dates(doc.company, [d], doc_name)
            if recheck["has_conflict"]:
                c = recheck["conflicts"][0]
                raise Exception(_(
                    "{0} sanasi shu orada boshqa import tomonidan yozildi "
                    "({1} → {2}) — to'xtatildi."
                ).format(c["date"], c["import_doc"], c["sales_invoice"]))

            try:
                # 5. Categorize by BOM (deep copy to prevent mutation across dates)
                date_items_copy = copy.deepcopy(date_items)
                categorized = bom_service.categorize_items_by_bom(date_items_copy)
                items_with_bom = categorized["with_bom"]
                
                # 6. Create Manufacture Stock Entries
                if items_with_bom:
                    config = StockEntryConfig(
                        company=doc.company,
                        warehouse=doc.source_warehouse,
                        posting_date=d,
                        allow_negative_stock=bool(doc.allow_negative_stock)
                    )
                    se_names = stock_service.create_manufacture_entries(items_with_bom, config, submit=True)
                    all_se_names.extend(se_names)
                    log(f"   ✅ {len(se_names)} ta Stock Entry yaratildi")
                    # Update doc incrementally
                    doc.db_set("stock_entry", ", ".join(all_se_names))
                
                # 7. Create Sales Invoice
                invoice_config = InvoiceConfig(
                    company=doc.company,
                    warehouse=doc.source_warehouse,
                    posting_date=d,
                    customer=doc.customer
                )
                si_name = invoice_service.create_sales_invoice(date_items, invoice_config, submit=True)
                all_si_names.append(si_name)
                # Hash DARHOL yoziladi — shunda import yarim yo'lda uzilsa
                # ham, keyingi urinishda fayl o'zgarganini aniqlay olamiz.
                if not doc.external_ref:
                    doc.db_set("external_ref", excel_hash)
                log(f"   ✅ Sales Invoice yaratildi: {si_name}")
                # Update doc incrementally
                doc.db_set("sales_invoice", ", ".join(all_si_names))
                
                totals = invoice_service.calculate_totals(date_items)
                total_amount += totals["total_amount"]
                
                frappe.db.commit()
                
            except Exception as date_err:
                frappe.db.rollback()
                log(f"   ❌ SANA {d} BO'YICHA XATO: {str(date_err)}")
                # After rollback, re-read doc to restore incremental SE/SI refs
                # that were committed in previous successful dates
                doc.reload()
                raise date_err

        # 8. Finalize
        doc.db_set("external_ref", excel_hash)
        doc.db_set("status", "Processed")
        
        log("\n" + "=" * 50)
        log("✅ IMPORT MUVAFFAQIYATLI YAKUNLANDI")
        log("=" * 50)
        log(f"📊 Jami sanalar: {len(sorted_dates)}")
        log(f"💰 Jami summa: {total_amount:,.0f} UZS")
        
        frappe.db.commit()
        
        return {
            "success": True,
            "message": _("Import muvaffaqiyatli"),
            "stock_entries": all_se_names,
            "sales_invoice": all_si_names,
            "total_items": len(valid_items),
            "total_amount": total_amount
        }
        
    except Exception as e:
        frappe.db.rollback()
        log(f"\n❌ XATO: {str(e)}")
        # Re-read doc after rollback to get last committed state
        doc.reload()
        doc.db_set("status", "Failed")
        # Tekshiruv xatosi bo'lsa — to'liq hisobot, aks holda xato matni
        doc.db_set("error_log", getattr(e, "report", "") or str(e))
        frappe.db.commit()
        frappe.log_error(f"Import Error: {doc_name}\n{str(e)}", "Daily Sales Import")
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def cancel_import(doc_name: str) -> Dict:
    """Cancel a processed import."""
    doc = frappe.get_doc("Jazira App Daily Sales Import", doc_name)
    
    if doc.status not in ["Processed", "Failed", "Processing"]:
        return {"success": False, "message": _("Faqat 'Processed', 'Failed' yoki 'Processing' statusdagi importni bekor qilish mumkin")}
    
    try:
        # Cancel Sales Invoices
        if doc.sales_invoice:
            si_names = [si.strip() for si in doc.sales_invoice.split(",") if si.strip()]
            for si in si_names:
                invoice_service.cancel_invoice(si)
        
        # Cancel Stock Entries
        if doc.stock_entry:
            se_names = [se.strip() for se in doc.stock_entry.split(",") if se.strip()]
            stock_service.cancel_stock_entries(se_names)
        
        doc.db_set("status", "Draft")
        doc.db_set("external_ref", "")
        doc.db_set("import_log", "")
        doc.db_set("stock_entry", "")
        doc.db_set("sales_invoice", "")
        doc.db_set("error_log", "")
        
        frappe.db.commit()
        return {"success": True, "message": _("Import bekor qilindi")}
    except Exception as e:
        frappe.db.rollback()
        return {"success": False, "message": str(e)}
