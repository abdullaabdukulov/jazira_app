from typing import Dict, List, Optional
from dataclasses import dataclass, field
from contextlib import contextmanager

import frappe
from frappe import _


@dataclass
class InvoiceConfig:
    """Configuration for Sales Invoice creation."""
    company: str
    warehouse: str
    posting_date: str
    customer: str = "Walk-in Customer"
    posting_time: str = "23:59:59"
    update_stock: bool = True


@dataclass
class InvoiceItem:
    """Sales Invoice item."""
    item_code: str
    qty: float
    rate: float
    warehouse: str = ""


class InvoiceService:
    """
    Service for Sales Invoice operations.
    
    Creates Sales Invoice with Update Stock enabled for restaurant workflow.
    """
    
    @contextmanager
    def _invoice_flags(self, mute_messages: bool = True):
        """Context manager for invoice operation flags."""
        original_mute = getattr(frappe.flags, "mute_messages", False)
        
        try:
            frappe.flags.mute_messages = mute_messages
            yield
        finally:
            frappe.flags.mute_messages = original_mute
    
    def create_sales_invoice(
        self,
        items: List[Dict],
        config: InvoiceConfig,
        submit: bool = True
    ) -> str:
        """
        Create Sales Invoice with Update Stock.
        
        Args:
            items: List of items with 'item_code', 'qty', 'rate' keys
            config: Invoice configuration
            submit: Whether to submit invoice
            
        Returns:
            Created Sales Invoice name
        """
        if not items:
            frappe.throw(_("Hech qanday item yo'q"))
        
        with self._invoice_flags(mute_messages=True):
            si = self._build_invoice(items, config)
            
            si.flags.ignore_permissions = True
            si.insert()
            
            if submit:
                si.submit()
            
            return si.name
    
    def _build_invoice(self, items: List[Dict], config: InvoiceConfig) -> "frappe.Document":
        """Build Sales Invoice document."""
        si = frappe.new_doc("Sales Invoice")
        
        # Header
        si.company = config.company
        si.customer = config.customer
        si.posting_date = config.posting_date
        si.posting_time = config.posting_time
        si.due_date = config.posting_date
        
        # Stock settings
        si.update_stock = 1 if config.update_stock else 0
        si.set_warehouse = config.warehouse
        
        # Items
        for item in items:
            si.append("items", {
                "item_code": item.get("item_code"),
                "qty": item.get("qty", 0),
                "rate": item.get("rate", 0),
                "warehouse": config.warehouse,
                "allow_zero_valuation_rate": 1
            })
        
        return si
    
    def cancel_invoice(self, invoice_name: str) -> bool:
        """
        Cancel a Sales Invoice.
        
        Args:
            invoice_name: Sales Invoice name
            
        Returns:
            True if cancelled successfully
        """
        if not invoice_name or not frappe.db.exists("Sales Invoice", invoice_name):
            return False
        
        try:
            si = frappe.get_doc("Sales Invoice", invoice_name)
            if si.docstatus == 1:
                si.cancel()
                return True
        except Exception:
            pass
        
        return False
    
    def calculate_totals(self, items: List[Dict]) -> Dict:
        """
        Calculate invoice totals.
        
        Args:
            items: List of items with 'qty' and 'rate'
            
        Returns:
            {total_qty: float, total_amount: float}
        """
        total_qty = sum(item.get("qty", 0) for item in items)
        total_amount = sum(
            item.get("qty", 0) * item.get("rate", 0)
            for item in items
        )
        
        return {
            "total_qty": total_qty,
            "total_amount": total_amount
        }


# Singleton instance
invoice_service = InvoiceService()
