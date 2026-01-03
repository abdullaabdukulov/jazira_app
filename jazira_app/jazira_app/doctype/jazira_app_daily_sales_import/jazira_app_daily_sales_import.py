# -*- coding: utf-8 -*-
# Copyright (c) 2024, Jazira App
# License: MIT
# Jazira App Daily Sales Import - ERPNext v15

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, cint, nowdate, get_datetime, getdate
import hashlib
import json
from typing import Dict, List, Tuple, Optional, Any


class JaziraAppDailySalesImport(Document):
    def validate(self):
        self.validate_warehouse_company()
        
    def validate_warehouse_company(self):
        if self.source_warehouse and self.company:
            warehouse_company = frappe.db.get_value("Warehouse", self.source_warehouse, "company")
            if warehouse_company and warehouse_company != self.company:
                frappe.throw(
                    _("Warehouse {0} does not belong to Company {1}").format(
                        self.source_warehouse, self.company
                    )
                )
    
    def before_submit(self):
        frappe.throw(_("This document cannot be submitted. Use 'Process Import' button."))


# =============================================================================
# HELPER: GET FISCAL YEAR (SIMPLE VERSION)
# =============================================================================

def get_fiscal_year_for_date(posting_date, company=None):
    """
    Get fiscal year for a given date using simple SQL query.
    """
    posting_date = getdate(posting_date)
    
    # Simple query to find fiscal year
    fiscal_year = frappe.db.sql("""
        SELECT fy.name
        FROM `tabFiscal Year` fy
        WHERE %s BETWEEN fy.year_start_date AND fy.year_end_date
        ORDER BY fy.year_start_date DESC
        LIMIT 1
    """, (posting_date,), as_dict=True)
    
    if fiscal_year:
        return fiscal_year[0].name
    
    # If not found, try to get default fiscal year
    default_fy = frappe.db.get_value("Fiscal Year", {"is_default": 1}, "name")
    if default_fy:
        return default_fy
    
    return None


# =============================================================================
# EXCEL READING FUNCTIONS
# =============================================================================

def parse_numeric(value: Any) -> float:
    """Parse numeric value from various formats."""
    if value is None:
        return 0.0
    
    if isinstance(value, (int, float)):
        return float(value)
    
    str_val = str(value).strip()
    if not str_val:
        return 0.0
    
    str_val = str_val.replace(" ", "")
    
    if "," in str_val:
        dots = str_val.count(".")
        commas = str_val.count(",")
        
        if commas == 1 and dots == 0:
            str_val = str_val.replace(",", ".")
        elif commas == 1 and dots >= 1:
            str_val = str_val.replace(".", "").replace(",", ".")
        elif dots == 0 and commas > 1:
            str_val = str_val.replace(",", "")
    
    if "." in str_val and str_val.count(".") == 1:
        parts = str_val.split(".")
        if len(parts[1]) == 3 and parts[1].isdigit():
            str_val = str_val.replace(".", "")
    
    try:
        return float(str_val)
    except ValueError:
        return 0.0


def read_excel_file(file_url: str) -> List[Dict]:
    """Read Excel file and return list of dictionaries."""
    try:
        from openpyxl import load_workbook
    except ImportError:
        frappe.throw(_("openpyxl kutubxonasi o'rnatilmagan. 'pip install openpyxl' buyrug'ini bajaring."))
    
    if file_url.startswith("/private/files/") or file_url.startswith("/files/"):
        file_path = frappe.get_site_path() + file_url
    else:
        file_doc = frappe.db.get_value("File", {"file_url": file_url}, ["file_url", "is_private"], as_dict=True)
        if file_doc:
            file_path = frappe.get_site_path() + file_doc.file_url
        else:
            file_path = frappe.get_site_path() + file_url
    
    wb = load_workbook(file_path, data_only=True)
    ws = wb.active
    
    COLUMN_MAP = {
        "наименование": "item_name",
        "количество": "qty",
        "количество, шт.": "qty",
        "количество, шт": "qty",
        "кол-во": "qty",
        "цена продажи": "rate",
        "цена продажи, uzs. коп.": "rate",
        "цена продажи, uzs": "rate",
        "цена": "rate",
    }
    
    header_row = None
    column_indices = {}
    
    for row_num, row in enumerate(ws.iter_rows(min_row=1, max_row=10), start=1):
        for col_num, cell in enumerate(row, start=1):
            if cell.value:
                cell_val = str(cell.value).lower().strip()
                for ru_header, field_name in COLUMN_MAP.items():
                    if ru_header in cell_val:
                        column_indices[field_name] = col_num
                        header_row = row_num
        
        if "item_name" in column_indices and "qty" in column_indices:
            break
    
    if not header_row or "item_name" not in column_indices:
        frappe.throw(_("Excel faylida 'Наименование' ustuni topilmadi."))
    
    if "qty" not in column_indices:
        frappe.throw(_("Excel faylida 'количество' ustuni topilmadi."))
    
    items = []
    for row_num, row in enumerate(ws.iter_rows(min_row=header_row + 1), start=header_row + 1):
        item_name_idx = column_indices["item_name"] - 1
        item_name = row[item_name_idx].value if item_name_idx < len(row) else None
        
        if not item_name or str(item_name).strip() == "":
            continue
        
        item_name = str(item_name).strip()
        
        skip_keywords = ["итого", "всего", "total", "сумма", "jami"]
        if any(kw in item_name.lower() for kw in skip_keywords):
            continue
        
        qty_idx = column_indices["qty"] - 1
        qty = parse_numeric(row[qty_idx].value if qty_idx < len(row) else 0)
        
        if qty <= 0:
            continue
        
        rate = 0.0
        if "rate" in column_indices:
            rate_idx = column_indices["rate"] - 1
            rate = parse_numeric(row[rate_idx].value if rate_idx < len(row) else 0)
        
        items.append({
            "item_name": item_name,
            "qty": qty,
            "rate": rate,
            "row_num": row_num
        })
    
    wb.close()
    return items


def calculate_excel_hash(file_url: str) -> str:
    """Calculate MD5 hash of Excel file for duplicate detection."""
    if file_url.startswith("/private/files/") or file_url.startswith("/files/"):
        file_path = frappe.get_site_path() + file_url
    else:
        file_doc = frappe.db.get_value("File", {"file_url": file_url}, "file_url")
        if file_doc:
            file_path = frappe.get_site_path() + file_doc
        else:
            file_path = frappe.get_site_path() + file_url
    
    try:
        with open(file_path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception:
        return ""


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

@frappe.whitelist()
def validate_before_upload(company: str, source_warehouse: str, posting_date: str) -> Dict:
    """Validate prerequisites before allowing Excel upload."""
    errors = []
    
    if not company:
        errors.append(_("Company tanlanmagan"))
    
    if not source_warehouse:
        errors.append(_("Source Warehouse (oshxona ombori) tanlanmagan"))
    
    if not posting_date:
        errors.append(_("Posting Date (savdo sanasi) tanlanmagan"))
    
    if company and source_warehouse:
        wh_company = frappe.db.get_value("Warehouse", source_warehouse, "company")
        if wh_company and wh_company != company:
            errors.append(
                _("Warehouse '{0}' kompaniyaga tegishli emas: {1}").format(
                    source_warehouse, company
                )
            )
    
    if not frappe.db.exists("Customer", "Walk-in Customer"):
        errors.append(_(
            "'Walk-in Customer' nomli mijoz topilmadi. "
            "Iltimos, avval yarating."
        ))
    
    # Check Fiscal Year
    if posting_date:
        fiscal_year = get_fiscal_year_for_date(posting_date, company)
        if not fiscal_year:
            errors.append(
                _("'{0}' sanasi uchun Fiscal Year topilmadi. "
                  "Accounting > Fiscal Year'da yarating.").format(posting_date)
            )
    
    if errors:
        return {"success": False, "message": "\n".join(errors)}
    
    return {"success": True, "message": _("Barcha tekshiruvlar muvaffaqiyatli o'tdi")}


@frappe.whitelist()
def validate_excel_items(doc_name: str) -> Dict:
    """Validate items in uploaded Excel file."""
    doc = frappe.get_doc("Jazira App Daily Sales Import", doc_name)
    
    if not doc.excel_file:
        return {"success": False, "message": _("Excel fayl yuklanmagan"), "errors": [], "items": []}
    
    try:
        excel_items = read_excel_file(doc.excel_file)
    except Exception as e:
        return {"success": False, "message": _("Excel o'qishda xato: {0}").format(str(e)), "errors": [], "items": []}
    
    if not excel_items:
        return {"success": False, "message": _("Excel faylda hech qanday sotuv topilmadi"), "errors": [], "items": []}
    
    errors = []
    valid_items = []
    
    for item in excel_items:
        item_name = item["item_name"]
        
        item_code = frappe.db.get_value("Item", {"item_name": item_name}, "name")
        
        if not item_code:
            item_code = frappe.db.get_value("Item", {"item_name": ["like", f"%{item_name}%"]}, "name")
        
        if not item_code:
            errors.append({
                "row": item["row_num"],
                "item_name": item_name,
                "error": _("Item topilmadi: '{0}'").format(item_name)
            })
        else:
            item["item_code"] = item_code
            item["found"] = True
            valid_items.append(item)
    
    if doc.excel_file:
        excel_hash = calculate_excel_hash(doc.excel_file)
        existing = frappe.db.exists(
            "Jazira App Daily Sales Import",
            {"external_ref": excel_hash, "name": ["!=", doc_name], "status": "Processed"}
        )
        if existing:
            errors.insert(0, {
                "row": 0,
                "item_name": "",
                "error": _("Bu Excel fayl avval import qilingan: {0}").format(existing)
            })
    
    return {
        "success": len(errors) == 0,
        "message": _("{0} ta item topildi, {1} ta xato").format(len(valid_items), len(errors)),
        "errors": errors,
        "items": valid_items,
        "total_qty": sum(i["qty"] for i in valid_items),
        "total_amount": sum(i["qty"] * i["rate"] for i in valid_items)
    }


# =============================================================================
# SALES INVOICE CREATION
# =============================================================================

def create_sales_invoice(doc: Document, items: List[Dict], submit: bool = True) -> str:
    """Create Sales Invoice for daily sales."""
    
    si = frappe.new_doc("Sales Invoice")
    si.company = doc.company
    si.customer = "Walk-in Customer"
    si.posting_date = doc.posting_date
    si.posting_time = "23:59:59"
    si.due_date = doc.posting_date
    si.update_stock = 0
    si.set_warehouse = doc.source_warehouse
    
    for item_data in items:
        si.append("items", {
            "item_code": item_data["item_code"],
            "qty": item_data["qty"],
            "rate": item_data["rate"],
            "warehouse": doc.source_warehouse
        })
    
    si.flags.ignore_permissions = True
    si.insert()
    
    if submit:
        si.submit()
    
    return si.name


# =============================================================================
# STOCK CONSUMPTION (BOM EXPLOSION)
# =============================================================================

def get_item_bom(item_code: str) -> Optional[str]:
    """Get default active BOM for an item."""
    bom = frappe.db.get_value(
        "BOM",
        {"item": item_code, "is_default": 1, "is_active": 1, "docstatus": 1},
        "name"
    )
    return bom


def explode_bom(bom_name: str, qty: float) -> List[Dict]:
    """Explode BOM to get ingredients with quantities."""
    from frappe.query_builder import DocType
    
    BOMItem = DocType("BOM Item")
    
    bom_items = (
        frappe.qb.from_(BOMItem)
        .select(BOMItem.item_code, BOMItem.qty, BOMItem.uom, BOMItem.stock_qty, BOMItem.stock_uom)
        .where(BOMItem.parent == bom_name)
        .run(as_dict=True)
    )
    
    bom_qty = frappe.db.get_value("BOM", bom_name, "quantity") or 1
    
    ingredients = []
    for bi in bom_items:
        required_qty = (bi.stock_qty / bom_qty) * qty
        ingredients.append({
            "item_code": bi.item_code,
            "qty": required_qty,
            "uom": bi.stock_uom or bi.uom
        })
    
    return ingredients


def process_stock_consumption(doc: Document, items: List[Dict], submit: bool = True) -> Optional[str]:
    """Process stock consumption based on BOM."""
    
    consumption_items = []
    log_entries = []
    
    for item_data in items:
        item_code = item_data["item_code"]
        qty = item_data["qty"]
        
        bom = get_item_bom(item_code)
        
        if bom:
            ingredients = explode_bom(bom, qty)
            log_entries.append(f"TAOM: {item_data['item_name']} x {qty} -> BOM: {bom}")
            for ing in ingredients:
                consumption_items.append({
                    "item_code": ing["item_code"],
                    "qty": ing["qty"],
                    "uom": ing["uom"],
                    "source": f"BOM: {item_data['item_name']}"
                })
                log_entries.append(f"  - {ing['item_code']}: {ing['qty']} {ing['uom']}")
        else:
            item_uom = frappe.db.get_value("Item", item_code, "stock_uom") or "Nos"
            consumption_items.append({
                "item_code": item_code,
                "qty": qty,
                "uom": item_uom,
                "source": f"Direct: {item_data['item_name']}"
            })
            log_entries.append(f"ICHIMLIK/TAYYOR: {item_data['item_name']} x {qty} {item_uom}")
    
    # Aggregate same items
    aggregated = {}
    for ci in consumption_items:
        key = ci["item_code"]
        if key in aggregated:
            aggregated[key]["qty"] += ci["qty"]
        else:
            aggregated[key] = ci.copy()
    
    if not aggregated:
        return None
    
    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = "Material Issue"
    se.company = doc.company
    se.posting_date = doc.posting_date
    se.posting_time = "23:59:59"
    
    for item_code, data in aggregated.items():
        se.append("items", {
            "item_code": item_code,
            "qty": data["qty"],
            "s_warehouse": doc.source_warehouse,
            "uom": data["uom"],
            "allow_zero_valuation_rate": 1
        })
    
    if doc.allow_negative_stock:
        frappe.flags.allow_negative_stock = True
    
    se.flags.ignore_permissions = True
    
    try:
        se.insert()
        if submit:
            se.submit()
    finally:
        frappe.flags.allow_negative_stock = False
    
    doc.db_set("import_log", "\n".join(log_entries))
    
    return se.name


# =============================================================================
# MAIN PROCESSING FUNCTION
# =============================================================================

@frappe.whitelist()
def process_import(doc_name: str, background: bool = False) -> Dict:
    """Main function to process the import."""
    if background:
        frappe.enqueue(
            _process_import_background,
            queue="long",
            timeout=3600,
            doc_name=doc_name
        )
        return {"success": True, "message": _("Import jarayoni fonada boshlandi")}
    
    return _process_import_sync(doc_name)


def _process_import_background(doc_name: str):
    """Background job for processing import."""
    try:
        result = _process_import_sync(doc_name)
        if not result["success"]:
            frappe.publish_realtime(
                "restaurant_import_failed",
                {"doc_name": doc_name, "error": result["message"]},
                doctype="Jazira App Daily Sales Import",
                docname=doc_name
            )
        else:
            frappe.publish_realtime(
                "restaurant_import_success",
                {"doc_name": doc_name, "result": result},
                doctype="Jazira App Daily Sales Import",
                docname=doc_name
            )
    except Exception as e:
        frappe.log_error(f"Jazira Import Error: {doc_name}\n{str(e)}", "Jazira App Daily Sales Import")
        doc = frappe.get_doc("Jazira App Daily Sales Import", doc_name)
        doc.db_set("status", "Failed")
        doc.db_set("error_log", str(e))


def _process_import_sync(doc_name: str) -> Dict:
    """Synchronous import processing."""
    doc = frappe.get_doc("Jazira App Daily Sales Import", doc_name)
    
    doc.db_set("status", "Processing")
    doc.db_set("error_log", "")
    
    try:
        validation = validate_before_upload(doc.company, doc.source_warehouse, str(doc.posting_date))
        if not validation["success"]:
            raise Exception(validation["message"])
        
        excel_items = read_excel_file(doc.excel_file)
        if not excel_items:
            raise Exception(_("Excel faylda sotuv topilmadi"))
        
        excel_hash = calculate_excel_hash(doc.excel_file)
        
        existing = frappe.db.exists(
            "Jazira App Daily Sales Import",
            {"external_ref": excel_hash, "name": ["!=", doc_name], "status": "Processed"}
        )
        if existing:
            raise Exception(_("Bu Excel avval import qilingan: {0}").format(existing))
        
        errors = []
        valid_items = []
        
        for item in excel_items:
            item_code = frappe.db.get_value("Item", {"item_name": item["item_name"]}, "name")
            
            if not item_code:
                errors.append(_("Qator {0}: Item topilmadi - '{1}'").format(item["row_num"], item["item_name"]))
            else:
                item["item_code"] = item_code
                valid_items.append(item)
        
        if errors:
            raise Exception("\n".join(errors))
        
        si_name = create_sales_invoice(doc, valid_items, submit=True)
        doc.db_set("sales_invoice", si_name)
        
        se_name = process_stock_consumption(doc, valid_items, submit=True)
        if se_name:
            doc.db_set("stock_entry", se_name)
        
        doc.db_set("external_ref", excel_hash)
        doc.db_set("status", "Processed")
        
        frappe.db.commit()
        
        return {
            "success": True,
            "message": _("Import muvaffaqiyatli bajarildi"),
            "sales_invoice": si_name,
            "stock_entry": se_name,
            "items_count": len(valid_items),
            "total_amount": sum(i["qty"] * i["rate"] for i in valid_items)
        }
        
    except Exception as e:
        frappe.db.rollback()
        doc.db_set("status", "Failed")
        doc.db_set("error_log", str(e))
        frappe.log_error(f"Jazira Import Error: {doc_name}\n{str(e)}", "Jazira App Daily Sales Import")
        return {"success": False, "message": str(e)}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

@frappe.whitelist()
def get_preview_data(doc_name: str) -> Dict:
    """Get preview of Excel data before processing."""
    doc = frappe.get_doc("Jazira App Daily Sales Import", doc_name)
    
    if not doc.excel_file:
        return {"success": False, "message": _("Excel fayl yuklanmagan")}
    
    try:
        items = read_excel_file(doc.excel_file)
        
        for item in items:
            item_code = frappe.db.get_value("Item", {"item_name": item["item_name"]}, "name")
            item["item_code"] = item_code
            item["found"] = bool(item_code)
            
            if item_code:
                bom = get_item_bom(item_code)
                item["has_bom"] = bool(bom)
                item["bom"] = bom
                item["type"] = "TAOM" if bom else "ICHIMLIK"
            else:
                item["has_bom"] = False
                item["type"] = "NOMA'LUM"
        
        return {
            "success": True,
            "items": items,
            "summary": {
                "total_items": len(items),
                "found": len([i for i in items if i["found"]]),
                "not_found": len([i for i in items if not i["found"]]),
                "dishes": len([i for i in items if i.get("has_bom")]),
                "drinks": len([i for i in items if i["found"] and not i.get("has_bom")]),
                "total_qty": sum(i["qty"] for i in items),
                "total_amount": sum(i["qty"] * i["rate"] for i in items)
            }
        }
        
    except Exception as e:
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def cancel_import(doc_name: str) -> Dict:
    """Cancel a processed import - cancels related documents."""
    doc = frappe.get_doc("Jazira App Daily Sales Import", doc_name)
    
    if doc.status != "Processed":
        return {"success": False, "message": _("Faqat 'Processed' statusdagi importni bekor qilish mumkin")}
    
    try:
        if doc.stock_entry:
            se = frappe.get_doc("Stock Entry", doc.stock_entry)
            if se.docstatus == 1:
                se.cancel()
        
        if doc.sales_invoice:
            si = frappe.get_doc("Sales Invoice", doc.sales_invoice)
            if si.docstatus == 1:
                si.cancel()
        
        doc.db_set("status", "Draft")
        doc.db_set("external_ref", "")
        
        frappe.db.commit()
        
        return {"success": True, "message": _("Import bekor qilindi")}
        
    except Exception as e:
        frappe.db.rollback()
        return {"success": False, "message": str(e)}