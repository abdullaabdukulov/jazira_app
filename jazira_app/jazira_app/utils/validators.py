from typing import Dict, List

import frappe
from frappe import _


class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass


def validate_import_prerequisites(
    company: str,
    source_warehouse: str,
    posting_date: str
) -> Dict:
    """
    Validate all prerequisites before import.
    
    Args:
        company: Company name
        source_warehouse: Warehouse name
        posting_date: Posting date string
        
    Returns:
        dict: {success: bool, message: str, errors: list}
    """
    errors = []
    
    # Required fields
    if not company:
        errors.append(_("Company tanlanmagan"))
    
    if not source_warehouse:
        errors.append(_("Ombor tanlanmagan"))
    
    if not posting_date:
        errors.append(_("Sana tanlanmagan"))
    
    # Warehouse belongs to company
    if company and source_warehouse:
        wh_company = frappe.db.get_value("Warehouse", source_warehouse, "company")
        if wh_company and wh_company != company:
            errors.append(
                _("Warehouse '{0}' kompaniyaga tegishli emas: {1}").format(
                    source_warehouse, company
                )
            )
    
    # Walk-in Customer exists
    if not frappe.db.exists("Customer", "Walk-in Customer"):
        errors.append(_("'Walk-in Customer' nomli mijoz topilmadi"))
    
    return {
        "success": len(errors) == 0,
        "message": "\n".join(errors) if errors else _("Tekshiruvlar muvaffaqiyatli"),
        "errors": errors
    }


def validate_warehouse_company(warehouse: str, company: str) -> bool:
    """
    Check if warehouse belongs to company.
    
    Args:
        warehouse: Warehouse name
        company: Company name
        
    Returns:
        bool: True if valid
        
    Raises:
        ValidationError: If warehouse doesn't belong to company
    """
    if not warehouse or not company:
        return True
    
    wh_company = frappe.db.get_value("Warehouse", warehouse, "company")
    
    if wh_company and wh_company != company:
        raise ValidationError(
            _("Warehouse {0} does not belong to Company {1}").format(
                warehouse, company
            )
        )
    
    return True


def validate_items_exist(items: List[Dict]) -> Dict:
    """
    Validate that all items exist in ERPNext.
    
    Args:
        items: List of items with 'item_name' key
        
    Returns:
        dict: {
            valid_items: list of items with item_code,
            errors: list of error dicts,
            success: bool
        }
    """
    valid_items = []
    errors = []
    
    for item in items:
        item_name = item.get("item_name", "")
        row_num = item.get("row_num", 0)
        
        # Try exact match first
        item_code = frappe.db.get_value("Item", {"item_name": item_name}, "name")
        
        # Try partial match
        if not item_code:
            item_code = frappe.db.get_value(
                "Item",
                {"item_name": ["like", f"%{item_name}%"]},
                "name"
            )
        
        if item_code:
            item["item_code"] = item_code
            item["found"] = True
            valid_items.append(item)
        else:
            errors.append({
                "row": row_num,
                "item_name": item_name,
                "error": _("Item topilmadi: '{0}'").format(item_name)
            })
    
    return {
        "valid_items": valid_items,
        "errors": errors,
        "success": len(errors) == 0
    }


def check_duplicate_import(excel_hash: str, current_doc_name: str) -> Dict:
    """
    Check if this Excel file was already imported.
    
    Args:
        excel_hash: MD5 hash of Excel file
        current_doc_name: Current document name to exclude
        
    Returns:
        dict: {is_duplicate: bool, existing_doc: str or None}
    """
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
    
    return {
        "is_duplicate": bool(existing),
        "existing_doc": existing
    }
