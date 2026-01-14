# -*- coding: utf-8 -*-
# Copyright (c) 2024, Jazira App and contributors
# For license information, please see license.txt

"""
Akt Sverka (Reconciliation Report)
==================================

Kontragent bilan o'zaro hisob-kitoblar sverka hisoboti.

Data Source: GL Entry ONLY
Double Counting: Prevented by using single source (GL Entry)

Accounting Logic:
- Opening Balance = SUM(debit - credit) before from_date
- Period Debit = SUM(debit) within period
- Period Credit = SUM(credit) within period
- Closing Balance = Opening + Period Debit - Period Credit

Balance Interpretation:
- Positive balance (Customer) = Customer owes us
- Negative balance (Customer) = We owe customer (advance received)
- Positive balance (Supplier) = We paid advance
- Negative balance (Supplier) = We owe supplier
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
    """Main entry point for Script Report."""
    validate_filters(filters)
    columns = get_columns(filters)
    data = get_data(filters)
    return columns, data


def validate_filters(filters):
    """Validate required filters."""
    if not filters:
        frappe.throw(_("Filtrlar kiritilmagan"))
    
    required = ["company", "from_date", "to_date", "party_type", "party"]
    for field in required:
        if not filters.get(field):
            frappe.throw(_("{0} majburiy").format(field))
    
    if getdate(filters.from_date) > getdate(filters.to_date):
        frappe.throw(_("Boshlanish sanasi tugash sanasidan katta bo'lishi mumkin emas"))


def get_columns(filters):
    """Define report columns."""
    return [
        {
            "fieldname": "posting_date",
            "label": _("Sana"),
            "fieldtype": "Date",
            "width": 100
        },
        {
            "fieldname": "voucher_type",
            "label": _("Hujjat turi"),
            "fieldtype": "Data",
            "width": 130
        },
        {
            "fieldname": "voucher_no",
            "label": _("Hujjat raqami"),
            "fieldtype": "Dynamic Link",
            "options": "voucher_type",
            "width": 160
        },
        {
            "fieldname": "debit",
            "label": _("Debit"),
            "fieldtype": "Currency",
            "width": 130
        },
        {
            "fieldname": "credit",
            "label": _("Credit"),
            "fieldtype": "Currency",
            "width": 130
        },
        {
            "fieldname": "balance",
            "label": _("Qoldiq"),
            "fieldtype": "Currency",
            "width": 130
        },
        {
            "fieldname": "remarks",
            "label": _("Izoh"),
            "fieldtype": "Data",
            "width": 250
        }
    ]


def get_data(filters):
    """Get report data."""
    data = []
    
    # 1. Opening Balance
    opening_balance = get_opening_balance(filters)
    
    data.append({
        "posting_date": None,
        "voucher_type": "",
        "voucher_no": _("Boshlang'ich qoldiq"),
        "debit": flt(opening_balance) if opening_balance > 0 else 0,
        "credit": abs(flt(opening_balance)) if opening_balance < 0 else 0,
        "balance": opening_balance,
        "remarks": _("Davr boshidagi qoldiq"),
        "is_opening": 1
    })
    
    # 2. Period Transactions
    transactions = get_period_transactions(filters)
    
    running_balance = opening_balance
    total_debit = 0
    total_credit = 0
    
    for txn in transactions:
        running_balance += flt(txn.debit) - flt(txn.credit)
        total_debit += flt(txn.debit)
        total_credit += flt(txn.credit)
        
        data.append({
            "posting_date": txn.posting_date,
            "voucher_type": get_voucher_type_label(txn.voucher_type),
            "voucher_no": txn.voucher_no,
            "debit": txn.debit,
            "credit": txn.credit,
            "balance": running_balance,
            "remarks": txn.remarks or ""
        })
    
    # 3. Closing Balance Row
    data.append({
        "posting_date": None,
        "voucher_type": "",
        "voucher_no": _("JAMI / Yakuniy qoldiq"),
        "debit": total_debit,
        "credit": total_credit,
        "balance": running_balance,
        "remarks": get_balance_interpretation(filters.party_type, running_balance),
        "is_closing": 1
    })
    
    return data


def get_opening_balance(filters):
    """
    Calculate opening balance BEFORE from_date.
    
    Opening = SUM(debit) - SUM(credit) for all transactions before from_date
    """
    conditions = get_conditions(filters, for_opening=True)
    
    result = frappe.db.sql("""
        SELECT 
            COALESCE(SUM(debit), 0) - COALESCE(SUM(credit), 0) as opening_balance
        FROM `tabGL Entry`
        WHERE {conditions}
    """.format(conditions=conditions), filters, as_dict=True)
    
    return flt(result[0].opening_balance) if result else 0


def get_period_transactions(filters):
    """
    Get all transactions within the period.
    
    Returns list of GL Entry records with debit, credit, voucher info.
    """
    conditions = get_conditions(filters, for_opening=False)
    
    return frappe.db.sql("""
        SELECT 
            posting_date,
            voucher_type,
            voucher_no,
            debit,
            credit,
            remarks,
            creation
        FROM `tabGL Entry`
        WHERE {conditions}
        ORDER BY posting_date ASC, creation ASC
    """.format(conditions=conditions), filters, as_dict=True)


def get_conditions(filters, for_opening=False):
    """Build WHERE conditions for GL Entry query."""
    conditions = [
        "party_type = %(party_type)s",
        "party = %(party)s",
        "company = %(company)s",
        "is_cancelled = 0"
    ]
    
    if for_opening:
        conditions.append("posting_date < %(from_date)s")
    else:
        conditions.append("posting_date >= %(from_date)s")
        conditions.append("posting_date <= %(to_date)s")
    
    if filters.get("account"):
        conditions.append("account = %(account)s")
    
    return " AND ".join(conditions)


def get_voucher_type_label(voucher_type):
    """Get user-friendly voucher type label."""
    labels = {
        "Sales Invoice": "Sotuv fakturasi",
        "Purchase Invoice": "Xarid fakturasi",
        "Payment Entry": "To'lov",
        "Journal Entry": "Jurnal yozuvi",
        "Delivery Note": "Yetkazib berish",
        "Purchase Receipt": "Qabul qilish"
    }
    return labels.get(voucher_type, voucher_type)


def get_balance_interpretation(party_type, balance):
    """Get human-readable balance interpretation."""
    if abs(balance) < 0.01:
        return _("Hisob-kitob to'liq yakunlangan")
    
    if party_type == "Customer":
        if balance > 0:
            return _("Mijoz bizga qarzdor")
        else:
            return _("Biz mijozga qarzdormiz (avans olingan)")
    
    elif party_type == "Supplier":
        if balance > 0:
            return _("Biz avans to'lagan (supplier qaytarishi kerak)")
        else:
            return _("Biz yetkazib beruvchiga qarzdormiz")
    
    elif party_type == "Employee":
        if balance > 0:
            return _("Xodim qaytarishi kerak (avans)")
        else:
            return _("Biz xodimga qarzdormiz")
    
    return ""


# =============================================================================
# WHITELISTED HELPER METHODS
# =============================================================================

@frappe.whitelist()
def get_party_balance(party_type, party, company, as_of_date=None):
    """
    Get party balance as of specific date.
    
    Useful for dashboard widgets or quick lookups.
    
    Args:
        party_type: Customer/Supplier/Employee
        party: Party name
        company: Company name
        as_of_date: Date (default: today)
    
    Returns:
        float: Balance amount
    """
    if not as_of_date:
        as_of_date = frappe.utils.today()
    
    result = frappe.db.sql("""
        SELECT 
            COALESCE(SUM(debit), 0) - COALESCE(SUM(credit), 0) as balance
        FROM `tabGL Entry`
        WHERE party_type = %(party_type)s
            AND party = %(party)s
            AND company = %(company)s
            AND posting_date <= %(as_of_date)s
            AND is_cancelled = 0
    """, {
        "party_type": party_type,
        "party": party,
        "company": company,
        "as_of_date": as_of_date
    }, as_dict=True)
    
    return flt(result[0].balance) if result else 0


@frappe.whitelist()
def get_party_transactions(party_type, party, company, from_date, to_date):
    """
    Get party transactions for API usage.
    
    Returns list of transactions with running balance.
    """
    filters = {
        "party_type": party_type,
        "party": party,
        "company": company,
        "from_date": from_date,
        "to_date": to_date
    }
    
    opening = get_opening_balance(filters)
    transactions = get_period_transactions(filters)
    
    running = opening
    result = []
    
    for txn in transactions:
        running += flt(txn.debit) - flt(txn.credit)
        result.append({
            "date": str(txn.posting_date),
            "voucher_type": txn.voucher_type,
            "voucher_no": txn.voucher_no,
            "debit": flt(txn.debit),
            "credit": flt(txn.credit),
            "balance": running
        })
    
    return {
        "opening_balance": opening,
        "transactions": result,
        "closing_balance": running
    }
