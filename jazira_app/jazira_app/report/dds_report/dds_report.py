# -*- coding: utf-8 -*-
# Copyright (c) 2024, Jazira App and contributors
# For license information, please see license.txt

"""
DDS Report (Движение Денежных Средств)
======================================

Cash flow report showing:
1. Summary: Opening balance, Income, Expense, Closing balance
2. Details: Breakdown by party type (Customer, Supplier, Expenses, etc.)

Data Source: Kassa doctype
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
    """Main entry point."""
    validate_filters(filters)
    
    columns = get_columns()
    data = get_detail_data(filters)
    report_summary = get_summary(filters)
    
    return columns, data, None, None, report_summary


def validate_filters(filters):
    """Validate required filters."""
    if not filters:
        frappe.throw(_("Filtrlar kiritilmagan"))
    
    if not filters.get("from_date") or not filters.get("to_date"):
        frappe.throw(_("Sana oralig'i majburiy"))
    
    if getdate(filters.from_date) > getdate(filters.to_date):
        frappe.throw(_("Boshlanish sanasi tugash sanasidan katta bo'lishi mumkin emas"))


def get_columns():
    """Define report columns for detail table."""
    return [
        {
            "fieldname": "party_type",
            "label": _("Kontragent turi"),
            "fieldtype": "Data",
            "width": 250
        },
        {
            "fieldname": "kirim",
            "label": _("Kirim"),
            "fieldtype": "Currency",
            "width": 150
        },
        {
            "fieldname": "chiqim",
            "label": _("Chiqim"),
            "fieldtype": "Currency",
            "width": 150
        }
    ]


def get_summary(filters):
    """Get summary data for report header."""
    source_account = filters.get("source_account")
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    
    # Opening balance (before from_date)
    opening = get_opening_balance(source_account, from_date)
    
    # Period movements
    period_data = get_period_totals(source_account, from_date, to_date)
    prixod = flt(period_data.get("prixod", 0))
    rasxod = flt(period_data.get("rasxod", 0))
    
    # Closing balance
    closing = opening + prixod - rasxod
    
    return [
        {
            "label": _("Ostatok na nachalo"),
            "value": frappe.format_value(opening, {"fieldtype": "Currency"}),
            "datatype": "Currency",
            "indicator": "blue"
        },
        {
            "label": _("Prixod"),
            "value": frappe.format_value(prixod, {"fieldtype": "Currency"}),
            "datatype": "Currency",
            "indicator": "green"
        },
        {
            "label": _("Rasxod"),
            "value": frappe.format_value(rasxod, {"fieldtype": "Currency"}),
            "datatype": "Currency",
            "indicator": "red"
        },
        {
            "label": _("Ostatok na kones"),
            "value": frappe.format_value(closing, {"fieldtype": "Currency"}),
            "datatype": "Currency",
            "indicator": "blue"
        }
    ]


def get_opening_balance(source_account, from_date):
    """Get opening balance before from_date."""
    if not source_account:
        # No filter - sum all
        result = frappe.db.sql("""
            SELECT 
                COALESCE(SUM(CASE WHEN oborot = 'Приход' THEN summa ELSE 0 END), 0) -
                COALESCE(SUM(CASE WHEN oborot IN ('Расход', 'Перемещение') THEN summa ELSE 0 END), 0) as balance
            FROM `tabKassa`
            WHERE date < %(from_date)s AND docstatus = 1
        """, {"from_date": from_date}, as_dict=True)
    else:
        # With filter - check source_account for normal transactions
        # For Peremesheniya: source = chiqim, target = kirim
        result = frappe.db.sql("""
            SELECT 
                COALESCE(SUM(CASE 
                    WHEN oborot = 'Приход' AND source_account = %(source_account)s THEN summa 
                    WHEN oborot = 'Перемещение' AND target_account = %(source_account)s THEN summa
                    ELSE 0 
                END), 0) -
                COALESCE(SUM(CASE 
                    WHEN oborot = 'Расход' AND source_account = %(source_account)s THEN summa 
                    WHEN oborot = 'Перемещение' AND source_account = %(source_account)s THEN summa
                    ELSE 0 
                END), 0) as balance
            FROM `tabKassa`
            WHERE date < %(from_date)s AND docstatus = 1
        """, {
            "source_account": source_account,
            "from_date": from_date
        }, as_dict=True)
    
    return flt(result[0].balance) if result else 0


def get_period_totals(source_account, from_date, to_date):
    """Get total prixod and rasxod for the period."""
    if not source_account:
        # No filter - sum all
        result = frappe.db.sql("""
            SELECT 
                COALESCE(SUM(CASE WHEN oborot = 'Приход' THEN summa ELSE 0 END), 0) as prixod,
                COALESCE(SUM(CASE WHEN oborot IN ('Расход', 'Перемещение') THEN summa ELSE 0 END), 0) as rasxod
            FROM `tabKassa`
            WHERE date >= %(from_date)s 
                AND date <= %(to_date)s 
                AND docstatus = 1
        """, {
            "from_date": from_date,
            "to_date": to_date
        }, as_dict=True)
    else:
        # With filter - check source_account for normal transactions
        # For Peremesheniya: source = chiqim, target = kirim
        result = frappe.db.sql("""
            SELECT 
                COALESCE(SUM(CASE 
                    WHEN oborot = 'Приход' AND source_account = %(source_account)s THEN summa 
                    WHEN oborot = 'Перемещение' AND target_account = %(source_account)s THEN summa
                    ELSE 0 
                END), 0) as prixod,
                COALESCE(SUM(CASE 
                    WHEN oborot = 'Расход' AND source_account = %(source_account)s THEN summa 
                    WHEN oborot = 'Перемещение' AND source_account = %(source_account)s THEN summa
                    ELSE 0 
                END), 0) as rasxod
            FROM `tabKassa`
            WHERE date >= %(from_date)s 
                AND date <= %(to_date)s 
                AND docstatus = 1
        """, {
            "source_account": source_account,
            "from_date": from_date,
            "to_date": to_date
        }, as_dict=True)
    
    return result[0] if result else {"prixod": 0, "rasxod": 0}


def get_detail_data(filters):
    """Get detailed breakdown by party type."""
    source_account = filters.get("source_account")
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    
    conditions = [
        "date >= %(from_date)s",
        "date <= %(to_date)s",
        "docstatus = 1"
    ]
    
    if source_account:
        conditions.append("source_account = %(source_account)s")
    
    where_clause = " AND ".join(conditions)
    
    data = []
    total_kirim = 0
    total_chiqim = 0
    
    # 1. Get all party types with their totals (excluding Расходы and Перемещение)
    party_data = frappe.db.sql("""
        SELECT 
            party_type,
            COALESCE(SUM(CASE WHEN oborot = 'Приход' THEN summa ELSE 0 END), 0) as kirim,
            COALESCE(SUM(CASE WHEN oborot = 'Расход' THEN summa ELSE 0 END), 0) as chiqim
        FROM `tabKassa`
        WHERE {where_clause}
            AND party_type IS NOT NULL
            AND party_type != ''
            AND party_type != 'Расходы'
            AND oborot IN ('Приход', 'Расход')
        GROUP BY party_type
        ORDER BY party_type
    """.format(where_clause=where_clause), {
        "source_account": source_account,
        "from_date": from_date,
        "to_date": to_date
    }, as_dict=True)
    
    for row in party_data:
        if row.kirim > 0 or row.chiqim > 0:
            data.append({
                "party_type": row.party_type,
                "kirim": flt(row.kirim),
                "chiqim": flt(row.chiqim)
            })
            total_kirim += flt(row.kirim)
            total_chiqim += flt(row.chiqim)
    
    # 2. Get Expenses breakdown by expense_kontragent
    expense_data = frappe.db.sql("""
        SELECT 
            COALESCE(expense_kontragent, 'Boshqa xarajatlar') as expense_account,
            COALESCE(SUM(CASE WHEN oborot = 'Приход' THEN summa ELSE 0 END), 0) as kirim,
            COALESCE(SUM(CASE WHEN oborot = 'Расход' THEN summa ELSE 0 END), 0) as chiqim
        FROM `tabKassa`
        WHERE {where_clause}
            AND party_type = 'Расходы'
        GROUP BY expense_kontragent
        ORDER BY expense_kontragent
    """.format(where_clause=where_clause), {
        "source_account": source_account,
        "from_date": from_date,
        "to_date": to_date
    }, as_dict=True)
    
    for row in expense_data:
        if row.kirim > 0 or row.chiqim > 0:
            data.append({
                "party_type": row.expense_account or "Boshqa xarajatlar",
                "kirim": flt(row.kirim),
                "chiqim": flt(row.chiqim)
            })
            total_kirim += flt(row.kirim)
            total_chiqim += flt(row.chiqim)
    
    # 3. Get Peremesheniya (oborot = 'Перемещение')
    # For transfers, check both source_account AND target_account
    transfer_conditions = [
        "date >= %(from_date)s",
        "date <= %(to_date)s",
        "docstatus = 1",
        "oborot = 'Перемещение'"
    ]
    
    if source_account:
        transfer_conditions.append("(source_account = %(source_account)s OR target_account = %(source_account)s)")
    
    transfer_where = " AND ".join(transfer_conditions)
    
    transfer_data = frappe.db.sql("""
        SELECT 
            COALESCE(SUM(CASE WHEN source_account = %(source_account)s OR %(source_account)s IS NULL THEN summa ELSE 0 END), 0) as chiqim,
            COALESCE(SUM(CASE WHEN target_account = %(source_account)s THEN summa ELSE 0 END), 0) as kirim
        FROM `tabKassa`
        WHERE {transfer_where}
    """.format(transfer_where=transfer_where), {
        "source_account": source_account,
        "from_date": from_date,
        "to_date": to_date
    }, as_dict=True)
    
    if transfer_data and (flt(transfer_data[0].kirim) > 0 or flt(transfer_data[0].chiqim) > 0):
        data.append({
            "party_type": "Peremesheniya",
            "kirim": flt(transfer_data[0].kirim),
            "chiqim": flt(transfer_data[0].chiqim)
        })
        total_kirim += flt(transfer_data[0].kirim)
        total_chiqim += flt(transfer_data[0].chiqim)
    
    # 4. Get transactions without party_type (if any)
    other_data = frappe.db.sql("""
        SELECT 
            COALESCE(SUM(CASE WHEN oborot = 'Приход' THEN summa ELSE 0 END), 0) as kirim,
            COALESCE(SUM(CASE WHEN oborot = 'Расход' THEN summa ELSE 0 END), 0) as chiqim
        FROM `tabKassa`
        WHERE {where_clause}
            AND (party_type IS NULL OR party_type = '')
            AND oborot IN ('Приход', 'Расход')
    """.format(where_clause=where_clause), {
        "source_account": source_account,
        "from_date": from_date,
        "to_date": to_date
    }, as_dict=True)
    
    if other_data and (flt(other_data[0].kirim) > 0 or flt(other_data[0].chiqim) > 0):
        data.append({
            "party_type": "Boshqa",
            "kirim": flt(other_data[0].kirim),
            "chiqim": flt(other_data[0].chiqim)
        })
        total_kirim += flt(other_data[0].kirim)
        total_chiqim += flt(other_data[0].chiqim)
    
    # Add Itogo row at the beginning
    if data:
        data.insert(0, {
            "party_type": "<b>Itogo</b>",
            "kirim": total_kirim,
            "chiqim": total_chiqim
        })
    
    return data