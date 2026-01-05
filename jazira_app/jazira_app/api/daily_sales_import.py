from typing import Dict

import frappe
from frappe import _
from frappe.utils import nowdate

from jazira_app.jazira_app.utils import (
    calculate_file_hash,
    validate_import_prerequisites,
    validate_items_exist,
    check_duplicate_import
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
    """
    Get default warehouse for a company.
    
    Args:
        company: Company name
        
    Returns:
        {source_warehouse: str or None}
    """
    if not company:
        return {"source_warehouse": None}
    
    # Try "Stores" type first
    warehouse = frappe.db.get_value(
        "Warehouse",
        {"company": company, "is_group": 0, "warehouse_type": "Stores"},
        "name"
    )
    
    # Fallback to any non-group warehouse
    if not warehouse:
        warehouse = frappe.db.get_value(
            "Warehouse",
            {"company": company, "is_group": 0},
            "name"
        )
    
    return {"source_warehouse": warehouse}


@frappe.whitelist()
def get_preview_data(doc_name: str) -> Dict:
    """
    Get preview of Excel data before processing.
    
    Args:
        doc_name: Document name
        
    Returns:
        {success, items, summary} or {success: False, message}
    """
    doc = frappe.get_doc("Jazira App Daily Sales Import", doc_name)
    
    if not doc.excel_file:
        return {"success": False, "message": _("Excel fayl yuklanmagan")}
    
    try:
        # Read Excel
        items = excel_service.read_sales_report(doc.excel_file)
        
        # Validate items
        validation = validate_items_exist(items)
        valid_items = validation["valid_items"]
        
        # Categorize by BOM
        for item in items:
            if item.get("item_code"):
                bom = bom_service.get_default_bom(item["item_code"])
                item["has_bom"] = bool(bom)
                item["bom"] = bom
                item["type"] = "MANUFACTURE" if bom else "DIRECT SALE"
            else:
                item["has_bom"] = False
                item["type"] = "NOT FOUND"
        
        # Calculate summary
        found_items = [i for i in items if i.get("found")]
        summary = {
            "total_items": len(items),
            "found": len(found_items),
            "not_found": len(items) - len(found_items),
            "with_bom": len([i for i in items if i.get("has_bom")]),
            "without_bom": len([i for i in found_items if not i.get("has_bom")]),
            "total_qty": sum(i.get("qty", 0) for i in items),
            "total_amount": sum(i.get("qty", 0) * i.get("rate", 0) for i in items)
        }
        
        return {"success": True, "items": items, "summary": summary}
        
    except Exception as e:
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def validate_excel_items(doc_name: str) -> Dict:
    """
    Validate items in uploaded Excel file.
    
    Args:
        doc_name: Document name
        
    Returns:
        {success, items, errors, message}
    """
    doc = frappe.get_doc("Jazira App Daily Sales Import", doc_name)
    
    if not doc.excel_file:
        return {
            "success": False,
            "message": _("Excel fayl yuklanmagan"),
            "errors": [],
            "items": []
        }
    
    try:
        # Read Excel
        items = excel_service.read_sales_report(doc.excel_file)
        
        if not items:
            return {
                "success": False,
                "message": _("Excel faylda sotuv topilmadi"),
                "errors": [],
                "items": []
            }
        
        # Validate items
        validation = validate_items_exist(items)
        
        # Check duplicate
        excel_hash = calculate_file_hash(doc.excel_file)
        duplicate = check_duplicate_import(excel_hash, doc_name)
        
        errors = validation["errors"]
        if duplicate["is_duplicate"]:
            errors.insert(0, {
                "row": 0,
                "item_name": "",
                "error": _("Bu Excel avval import qilingan: {0}").format(
                    duplicate["existing_doc"]
                )
            })
        
        totals = invoice_service.calculate_totals(validation["valid_items"])
        
        return {
            "success": len(errors) == 0,
            "message": _("{0} ta item topildi, {1} ta xato").format(
                len(validation["valid_items"]), len(errors)
            ),
            "errors": errors,
            "items": validation["valid_items"],
            "total_qty": totals["total_qty"],
            "total_amount": totals["total_amount"]
        }
        
    except Exception as e:
        return {"success": False, "message": str(e), "errors": [], "items": []}


@frappe.whitelist()
def process_import(doc_name: str, background: bool = False) -> Dict:
    """
    Process the import - main entry point.
    
    Args:
        doc_name: Document name
        background: Run in background queue
        
    Returns:
        {success, message, stock_entries, sales_invoice, ...}
    """
    if background:
        frappe.enqueue(
            _process_import_job,
            queue="long",
            timeout=3600,
            doc_name=doc_name
        )
        return {"success": True, "message": _("Import fonada boshlandi")}
    
    return _process_import_sync(doc_name)


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
        frappe.log_error(f"Import Error: {doc_name}\n{str(e)}", "Daily Sales Import")
        doc = frappe.get_doc("Jazira App Daily Sales Import", doc_name)
        doc.db_set("status", "Failed")
        doc.db_set("error_log", str(e))


def _process_import_sync(doc_name: str) -> Dict:
    """
    Synchronous import processing.
    
    Workflow:
    1. Validate prerequisites
    2. Read Excel and validate items
    3. Categorize by BOM
    4. Create Manufacture Stock Entries (BOM items)
    5. Create Sales Invoice (all items)
    """
    doc = frappe.get_doc("Jazira App Daily Sales Import", doc_name)
    
    # Check idempotency
    if doc.status == "Processed":
        return {
            "success": False,
            "message": _("Bu import allaqachon bajarilgan")
        }
    
    # Update status
    doc.db_set("status", "Processing")
    doc.db_set("error_log", "")
    doc.db_set("import_log", f"Import boshlandi: {nowdate()}\n")
    
    try:
        # 1. Validate prerequisites
        validation = validate_import_prerequisites(
            doc.company,
            doc.source_warehouse,
            str(doc.posting_date)
        )
        if not validation["success"]:
            raise Exception(validation["message"])
        
        # 2. Read Excel
        items = excel_service.read_sales_report(doc.excel_file)
        if not items:
            raise Exception(_("Excel faylda sotuv topilmadi"))
        
        # 3. Check duplicate
        excel_hash = calculate_file_hash(doc.excel_file)
        duplicate = check_duplicate_import(excel_hash, doc_name)
        if duplicate["is_duplicate"]:
            raise Exception(
                _("Bu Excel avval import qilingan: {0}").format(duplicate["existing_doc"])
            )
        
        # 4. Validate and match items
        item_validation = validate_items_exist(items)
        if item_validation["errors"]:
            error_msgs = [e["error"] for e in item_validation["errors"]]
            raise Exception("\n".join(error_msgs))
        
        valid_items = item_validation["valid_items"]
        
        # 5. Categorize by BOM
        categorized = bom_service.categorize_items_by_bom(valid_items)
        items_with_bom = categorized["with_bom"]
        items_without_bom = categorized["without_bom"]
        
        # 6. Create Manufacture Stock Entries
        se_names = []
        if items_with_bom:
            config = StockEntryConfig(
                company=doc.company,
                warehouse=doc.source_warehouse,
                posting_date=str(doc.posting_date),
                allow_negative_stock=bool(doc.allow_negative_stock)
            )
            se_names = stock_service.create_manufacture_entries(
                items_with_bom, config, submit=True
            )
            if se_names:
                doc.db_set("stock_entry", ", ".join(se_names))
        
        # 7. Create Sales Invoice
        invoice_config = InvoiceConfig(
            company=doc.company,
            warehouse=doc.source_warehouse,
            posting_date=str(doc.posting_date),
            customer=doc.customer or "Walk-in Customer"
        )
        si_name = invoice_service.create_sales_invoice(
            valid_items, invoice_config, submit=True
        )
        doc.db_set("sales_invoice", si_name)
        
        # 8. Finalize
        doc.db_set("external_ref", excel_hash)
        doc.db_set("status", "Processed")
        
        totals = invoice_service.calculate_totals(valid_items)
        
        frappe.db.commit()
        
        return {
            "success": True,
            "message": _("Import muvaffaqiyatli"),
            "stock_entries": se_names,
            "sales_invoice": si_name,
            "items_with_bom": len(items_with_bom),
            "items_without_bom": len(items_without_bom),
            "total_items": len(valid_items),
            "total_amount": totals["total_amount"]
        }
        
    except Exception as e:
        frappe.db.rollback()
        doc.db_set("status", "Failed")
        doc.db_set("error_log", str(e))
        frappe.log_error(f"Import Error: {doc_name}\n{str(e)}", "Daily Sales Import")
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def cancel_import(doc_name: str) -> Dict:
    """
    Cancel a processed import.
    
    Args:
        doc_name: Document name
        
    Returns:
        {success, message}
    """
    doc = frappe.get_doc("Jazira App Daily Sales Import", doc_name)
    
    if doc.status != "Processed":
        return {
            "success": False,
            "message": _("Faqat 'Processed' statusdagi importni bekor qilish mumkin")
        }
    
    try:
        # Cancel Sales Invoice first
        if doc.sales_invoice:
            invoice_service.cancel_invoice(doc.sales_invoice)
        
        # Cancel Stock Entries
        if doc.stock_entry:
            se_names = [se.strip() for se in doc.stock_entry.split(",") if se.strip()]
            stock_service.cancel_stock_entries(se_names)
        
        # Reset document
        doc.db_set("status", "Draft")
        doc.db_set("external_ref", "")
        doc.db_set("import_log", "")
        
        frappe.db.commit()
        
        return {"success": True, "message": _("Import bekor qilindi")}
        
    except Exception as e:
        frappe.db.rollback()
        return {"success": False, "message": str(e)}
