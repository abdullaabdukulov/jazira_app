# -*- coding: utf-8 -*-
# Copyright (c) 2024, Jazira App and contributors
# For license information, please see license.txt

"""
Kontragent Report v2.1
======================

Barcha kontragentlar bo'yicha qarz va aylanma hisoboti.

Data Sources:
- GL Entry → Standard party types (Customer, Supplier, Employee, Shareholder)
- Kassa → Расходы (Expense accounts) va Прочее лицо (Kassa Kontragent)

⚠️ MUHIM:
- Расходы va Прочее лицо GL Entry da party sifatida saqlanMAYDI
- Shuning uchun ular bevosita Kassa jadvalidan o'qiladi

Qo'llab-quvvatlanadigan kontragent turlari:
- Customer → Mijozlar (Debitorlar)
- Supplier → Yetkazib beruvchilar (Kreditorlar)
- Employee → Xodimlar
- Shareholder → Aktsiyadorlar
- Расходы → Xarajat hisoblar
- Прочее лицо → Kassa Kontragent (boshqa shaxslar)
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
    """Main entry point."""
    validate_filters(filters)
    columns = get_columns(filters)
    data = get_data(filters)
    
    # Add summary rows with grouping
    data = add_summary_rows(data, filters)
    
    return columns, data


def validate_filters(filters):
    """Validate filters."""
    if not filters.get("company"):
        frappe.throw(_("Company majburiy"))
    if not filters.get("from_date") or not filters.get("to_date"):
        frappe.throw(_("Sana oralig'i majburiy"))
    
    if getdate(filters.from_date) > getdate(filters.to_date):
        frappe.throw(_("Boshlanish sanasi tugash sanasidan katta bo'lishi mumkin emas"))


def get_columns(filters):
    """Define columns."""
    return [
        {
            "fieldname": "party_type",
            "label": _("Turi"),
            "fieldtype": "Data",
            "width": 130
        },
        {
            "fieldname": "party",
            "label": _("Kontragent"),
            "fieldtype": "Data",
            "width": 180
        },
        {
            "fieldname": "party_name",
            "label": _("Nomi"),
            "fieldtype": "Data",
            "width": 200
        },
        {
            "fieldname": "opening_balance",
            "label": _("Boshlang'ich"),
            "fieldtype": "Currency",
            "width": 130
        },
        {
            "fieldname": "period_debit",
            "label": _("Debit"),
            "fieldtype": "Currency",
            "width": 130
        },
        {
            "fieldname": "period_credit",
            "label": _("Credit"),
            "fieldtype": "Currency",
            "width": 130
        },
        {
            "fieldname": "closing_balance",
            "label": _("Yakuniy qoldiq"),
            "fieldtype": "Currency",
            "width": 140
        }
    ]


def get_data(filters):
    """
    Get aggregated data by party from multiple sources.
    
    Sources:
    1. GL Entry → Customer, Supplier, Employee, Shareholder
    2. Kassa → Расходы (expense_kontragent field)
    3. Kassa → Прочее лицо (prochee_kontragent field)
    """
    data = []
    
    # 1. Standard party types from GL Entry
    party_data = get_gl_entry_party_data(filters)
    data.extend(party_data)
    
    # 2. Расходы (Expenses) from Kassa - if checkbox is checked or no filter
    if filters.get("include_expenses", 1) and (not filters.get("party_type") or filters.get("party_type") == "Расходы"):
        expense_data = get_kassa_expense_data(filters)
        data.extend(expense_data)
    
    # 3. Прочее лицо (Kassa Kontragent) from Kassa - if checkbox is checked or no filter
    if filters.get("include_prochie_litsa", 1) and (not filters.get("party_type") or filters.get("party_type") == "Прочее лицо"):
        prochie_data = get_kassa_prochie_litsa_data(filters)
        data.extend(prochie_data)
    
    return data


def get_gl_entry_party_data(filters):
    """
    Get standard party data from GL Entry.
    
    Party types: Customer, Supplier, Employee, Shareholder
    """
    conditions = [
        "company = %(company)s",
        "is_cancelled = 0",
        "posting_date <= %(to_date)s",
        "party IS NOT NULL",
        "party != ''"
    ]
    
    # Filter by standard party types only
    standard_types = ("Customer", "Supplier", "Employee", "Shareholder")
    
    if filters.get("party_type"):
        if filters.get("party_type") in standard_types:
            conditions.append("party_type = %(party_type)s")
        else:
            # Non-standard party type selected (Расходы or Прочее лицо)
            # Skip GL Entry data - will be handled by Kassa queries
            return []
    else:
        conditions.append("party_type IN ('Customer', 'Supplier', 'Employee', 'Shareholder')")
    
    if filters.get("party"):
        conditions.append("party = %(party)s")
    
    where_clause = " AND ".join(conditions)
    
    data = frappe.db.sql("""
        SELECT 
            party_type,
            party,
            
            -- Opening balance (before from_date)
            SUM(CASE 
                WHEN posting_date < %(from_date)s 
                THEN debit - credit 
                ELSE 0 
            END) as opening_balance,
            
            -- Period debit
            SUM(CASE 
                WHEN posting_date >= %(from_date)s AND posting_date <= %(to_date)s 
                THEN debit 
                ELSE 0 
            END) as period_debit,
            
            -- Period credit
            SUM(CASE 
                WHEN posting_date >= %(from_date)s AND posting_date <= %(to_date)s 
                THEN credit 
                ELSE 0 
            END) as period_credit,
            
            -- Closing balance
            SUM(debit - credit) as closing_balance
            
        FROM `tabGL Entry`
        WHERE {where_clause}
        GROUP BY party_type, party
        HAVING (
            ABS(closing_balance) > 0.01 
            OR period_debit > 0.01 
            OR period_credit > 0.01
            OR %(show_zero_balance)s = 1
        )
        ORDER BY party_type, party
    """.format(where_clause=where_clause), {
        **filters,
        "show_zero_balance": filters.get("show_zero_balance", 0)
    }, as_dict=True)
    
    # Add party names
    for row in data:
        row["party_name"] = get_party_name(row.party_type, row.party)
    
    return data


def get_kassa_expense_data(filters):
    """
    Get Expense (Расходы) data from Kassa.
    
    Kassa party_type='Расходы' → expense_kontragent (Account)
    
    Note: Expenses are always OUTFLOW (Расход operation), so:
    - Debit = expense amount
    - Credit = 0
    - Balance = total expenses
    """
    # Check if Kassa doctype exists
    if not frappe.db.exists("DocType", "Kassa"):
        return []
    
    conditions = [
        "k.company = %(company)s",
        "k.docstatus = 1",
        "k.party_type = 'Расходы'",
        "k.expense_kontragent IS NOT NULL",
        "k.expense_kontragent != ''"
    ]
    
    if filters.get("party"):
        conditions.append("k.expense_kontragent = %(party)s")
    
    where_clause = " AND ".join(conditions)
    
    data = frappe.db.sql("""
        SELECT 
            'Расходы' as party_type,
            k.expense_kontragent as party,
            
            -- Opening balance (before from_date) - total expenses before period
            COALESCE(SUM(CASE 
                WHEN k.date < %(from_date)s 
                THEN k.summa 
                ELSE 0 
            END), 0) as opening_balance,
            
            -- Period debit (expense = debit)
            COALESCE(SUM(CASE 
                WHEN k.date >= %(from_date)s AND k.date <= %(to_date)s 
                THEN k.summa 
                ELSE 0 
            END), 0) as period_debit,
            
            -- Period credit (no credit for expenses)
            0 as period_credit,
            
            -- Closing balance (total expenses)
            COALESCE(SUM(k.summa), 0) as closing_balance
            
        FROM `tabKassa` k
        WHERE {where_clause}
            AND k.date <= %(to_date)s
        GROUP BY k.expense_kontragent
        HAVING (
            closing_balance > 0.01 
            OR period_debit > 0.01
            OR %(show_zero_balance)s = 1
        )
        ORDER BY k.expense_kontragent
    """.format(where_clause=where_clause), {
        **filters,
        "show_zero_balance": filters.get("show_zero_balance", 0)
    }, as_dict=True)
    
    # Get account names for party_name
    for row in data:
        account_name = frappe.db.get_value("Account", row.party, "account_name")
        row["party_name"] = account_name if account_name else row.party
    
    return data


def get_kassa_prochie_litsa_data(filters):
    """
    Get Прочее лицо (Kassa Kontragent) data from Kassa.
    
    Kassa party_type='Прочее лицо' → prochee_kontragent
    
    Logic:
    - Приход (income) = we received money → Credit (negative balance)
    - Расход (expense) = we gave money → Debit (positive balance)
    
    Positive balance = they owe us (we gave them money)
    Negative balance = we owe them (they gave us money)
    """
    # Check if Kassa doctype exists
    if not frappe.db.exists("DocType", "Kassa"):
        return []
    
    conditions = [
        "k.company = %(company)s",
        "k.docstatus = 1",
        "k.party_type = 'Прочее лицо'",
        "k.prochee_kontragent IS NOT NULL",
        "k.prochee_kontragent != ''"
    ]
    
    if filters.get("party"):
        conditions.append("k.prochee_kontragent = %(party)s")
    
    where_clause = " AND ".join(conditions)
    
    data = frappe.db.sql("""
        SELECT 
            'Прочее лицо' as party_type,
            k.prochee_kontragent as party,
            
            -- Opening balance (before from_date)
            COALESCE(SUM(CASE 
                WHEN k.date < %(from_date)s THEN
                    CASE 
                        WHEN k.oborot = 'Расход' THEN k.summa
                        WHEN k.oborot = 'Приход' THEN -k.summa
                        ELSE 0
                    END
                ELSE 0 
            END), 0) as opening_balance,
            
            -- Period debit (Расход = we gave money)
            COALESCE(SUM(CASE 
                WHEN k.date >= %(from_date)s AND k.date <= %(to_date)s 
                    AND k.oborot = 'Расход'
                THEN k.summa 
                ELSE 0 
            END), 0) as period_debit,
            
            -- Period credit (Приход = we received money)
            COALESCE(SUM(CASE 
                WHEN k.date >= %(from_date)s AND k.date <= %(to_date)s 
                    AND k.oborot = 'Приход'
                THEN k.summa 
                ELSE 0 
            END), 0) as period_credit,
            
            -- Closing balance
            COALESCE(SUM(CASE 
                WHEN k.oborot = 'Расход' THEN k.summa
                WHEN k.oborot = 'Приход' THEN -k.summa
                ELSE 0
            END), 0) as closing_balance
            
        FROM `tabKassa` k
        WHERE {where_clause}
            AND k.date <= %(to_date)s
        GROUP BY k.prochee_kontragent
        HAVING (
            ABS(closing_balance) > 0.01 
            OR period_debit > 0.01 
            OR period_credit > 0.01
            OR %(show_zero_balance)s = 1
        )
        ORDER BY k.prochee_kontragent
    """.format(where_clause=where_clause), {
        **filters,
        "show_zero_balance": filters.get("show_zero_balance", 0)
    }, as_dict=True)
    
    # Get kontragent names from Kassa Kontragent doctype
    for row in data:
        if frappe.db.exists("DocType", "Kassa Kontragent"):
            kontragent_name = frappe.db.get_value("Kassa Kontragent", row.party, "kontragent_name")
            row["party_name"] = kontragent_name if kontragent_name else row.party
        else:
            row["party_name"] = row.party
    
    return data


def get_party_name(party_type, party):
    """Get party name based on type."""
    if not party_type or not party:
        return ""
    
    fieldname_map = {
        "Customer": "customer_name",
        "Supplier": "supplier_name",
        "Employee": "employee_name",
        "Shareholder": "title"
    }
    
    fieldname = fieldname_map.get(party_type, "name")
    
    try:
        return frappe.db.get_value(party_type, party, fieldname) or party
    except Exception:
        return party


def add_summary_rows(data, filters):
    """Add summary rows by party_type."""
    if not data:
        return data
    
    # Group by party_type
    grouped = {}
    for row in data:
        pt = row.get("party_type")
        if not pt:
            continue
        if pt not in grouped:
            grouped[pt] = {
                "opening_balance": 0,
                "period_debit": 0,
                "period_credit": 0,
                "closing_balance": 0,
                "rows": []
            }
        grouped[pt]["opening_balance"] += flt(row.get("opening_balance"))
        grouped[pt]["period_debit"] += flt(row.get("period_debit"))
        grouped[pt]["period_credit"] += flt(row.get("period_credit"))
        grouped[pt]["closing_balance"] += flt(row.get("closing_balance"))
        grouped[pt]["rows"].append(row)
    
    # Build result with subtotals
    result = []
    grand_total = {
        "opening_balance": 0,
        "period_debit": 0,
        "period_credit": 0,
        "closing_balance": 0
    }
    
    # Sort party types for consistent display
    party_type_order = ["Customer", "Supplier", "Employee", "Shareholder", "Расходы", "Прочее лицо"]
    sorted_types = sorted(grouped.keys(), key=lambda x: party_type_order.index(x) if x in party_type_order else 99)
    
    for party_type in sorted_types:
        group = grouped[party_type]
        
        # Add party_type header
        result.append({
            "party_type": get_party_type_label(party_type),
            "party": "",
            "party_name": _("{0} ta kontragent").format(len(group["rows"])),
            "opening_balance": None,
            "period_debit": None,
            "period_credit": None,
            "closing_balance": None,
            "is_group_header": 1
        })
        
        # Add rows
        for row in group["rows"]:
            result.append(row)
        
        # Add subtotal
        result.append({
            "party_type": "",
            "party": "",
            "party_name": _("{0} jami").format(get_party_type_label(party_type)),
            "opening_balance": group["opening_balance"],
            "period_debit": group["period_debit"],
            "period_credit": group["period_credit"],
            "closing_balance": group["closing_balance"],
            "is_subtotal": 1
        })
        
        # Add blank row
        result.append({})
        
        # Accumulate grand total
        grand_total["opening_balance"] += group["opening_balance"]
        grand_total["period_debit"] += group["period_debit"]
        grand_total["period_credit"] += group["period_credit"]
        grand_total["closing_balance"] += group["closing_balance"]
    
    # Add grand total
    result.append({
        "party_type": "",
        "party": "",
        "party_name": _("UMUMIY JAMI"),
        "opening_balance": grand_total["opening_balance"],
        "period_debit": grand_total["period_debit"],
        "period_credit": grand_total["period_credit"],
        "closing_balance": grand_total["closing_balance"],
        "is_grand_total": 1
    })
    
    return result


def get_party_type_label(party_type):
    """Get user-friendly party type label."""
    labels = {
        "Customer": "📦 Mijozlar (Debitorlar)",
        "Supplier": "🚚 Yetkazib beruvchilar (Kreditorlar)",
        "Employee": "👤 Xodimlar",
        "Shareholder": "📊 Aktsiyadorlar",
        "Расходы": "💰 Xarajatlar (Расходы)",
        "Прочее лицо": "👥 Boshqa shaxslar (Прочее лицо)"
    }
    return labels.get(party_type, party_type)


# =============================================================================
# WHITELISTED HELPER METHODS
# =============================================================================

@frappe.whitelist()
def get_all_party_balances(company, as_of_date=None):
    """
    Get all party balances for dashboard.
    
    Returns summary by party type including Kassa-based entries.
    """
    if not as_of_date:
        as_of_date = frappe.utils.today()
    
    result = []
    
    # GL Entry based parties
    gl_summary = frappe.db.sql("""
        SELECT 
            party_type,
            COUNT(DISTINCT party) as party_count,
            SUM(debit - credit) as total_balance,
            SUM(CASE WHEN (debit - credit) > 0 THEN (debit - credit) ELSE 0 END) as debit_balance,
            SUM(CASE WHEN (debit - credit) < 0 THEN ABS(debit - credit) ELSE 0 END) as credit_balance
        FROM `tabGL Entry`
        WHERE company = %(company)s
            AND posting_date <= %(as_of_date)s
            AND is_cancelled = 0
            AND party IS NOT NULL
            AND party != ''
            AND party_type IN ('Customer', 'Supplier', 'Employee', 'Shareholder')
        GROUP BY party_type
        ORDER BY party_type
    """, {
        "company": company,
        "as_of_date": as_of_date
    }, as_dict=True)
    
    result.extend(gl_summary)
    
    # Kassa based - Расходы
    if frappe.db.exists("DocType", "Kassa"):
        expense_summary = frappe.db.sql("""
            SELECT 
                'Расходы' as party_type,
                COUNT(DISTINCT expense_kontragent) as party_count,
                SUM(summa) as total_balance,
                SUM(summa) as debit_balance,
                0 as credit_balance
            FROM `tabKassa`
            WHERE company = %(company)s
                AND date <= %(as_of_date)s
                AND docstatus = 1
                AND party_type = 'Расходы'
                AND expense_kontragent IS NOT NULL
                AND expense_kontragent != ''
        """, {
            "company": company,
            "as_of_date": as_of_date
        }, as_dict=True)
        
        if expense_summary and expense_summary[0].party_count:
            result.extend(expense_summary)
        
        # Kassa based - Прочее лицо
        prochie_summary = frappe.db.sql("""
            SELECT 
                'Прочее лицо' as party_type,
                COUNT(DISTINCT prochee_kontragent) as party_count,
                SUM(CASE 
                    WHEN oborot = 'Расход' THEN summa
                    WHEN oborot = 'Приход' THEN -summa
                    ELSE 0
                END) as total_balance,
                SUM(CASE WHEN oborot = 'Расход' THEN summa ELSE 0 END) as debit_balance,
                SUM(CASE WHEN oborot = 'Приход' THEN summa ELSE 0 END) as credit_balance
            FROM `tabKassa`
            WHERE company = %(company)s
                AND date <= %(as_of_date)s
                AND docstatus = 1
                AND party_type = 'Прочее лицо'
                AND prochee_kontragent IS NOT NULL
                AND prochee_kontragent != ''
        """, {
            "company": company,
            "as_of_date": as_of_date
        }, as_dict=True)
        
        if prochie_summary and prochie_summary[0].party_count:
            result.extend(prochie_summary)
    
    return result


@frappe.whitelist()
def get_expense_breakdown(company, from_date, to_date):
    """Get expense breakdown by account."""
    if not frappe.db.exists("DocType", "Kassa"):
        return []
    
    return frappe.db.sql("""
        SELECT 
            expense_kontragent as account,
            SUM(summa) as total_amount,
            COUNT(*) as entry_count
        FROM `tabKassa`
        WHERE company = %(company)s
            AND date >= %(from_date)s
            AND date <= %(to_date)s
            AND docstatus = 1
            AND party_type = 'Расходы'
            AND expense_kontragent IS NOT NULL
        GROUP BY expense_kontragent
        ORDER BY total_amount DESC
        LIMIT 20
    """, {
        "company": company,
        "from_date": from_date,
        "to_date": to_date
    }, as_dict=True)
