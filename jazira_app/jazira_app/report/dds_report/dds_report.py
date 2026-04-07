# Copyright (c) 2024, Jazira App and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate
from html import escape


def execute(filters=None):
    validate_filters(filters)
    columns = get_columns()
    data, expense_summaries, opening, closing = get_data(filters)
    summary_html = get_summary_html(data, expense_summaries, opening, closing)
    return columns, data, summary_html


def validate_filters(filters):
    if not filters:
        frappe.throw(_("Filtrlar kiritilmagan"))
    if not filters.get("from_date") or not filters.get("to_date"):
        frappe.throw(_("Sana oralig'i majburiy"))
    if getdate(filters["from_date"]) > getdate(filters["to_date"]):
        frappe.throw(_("Boshlanish sanasi tugash sanasidan katta bo'lishi mumkin emas"))


def get_columns():
    return [
        {"fieldname": "date",          "label": _("Sana"),       "fieldtype": "Date",     "width": 100},
        {"fieldname": "source_account","label": _("Kassa"),       "fieldtype": "Link",     "options": "Mode of Payment", "width": 160},
        {"fieldname": "direction",     "label": _("Yo'nalish"),  "fieldtype": "Data",     "width": 110},
        {"fieldname": "party_type",    "label": _("Kategoriya"), "fieldtype": "Data",     "width": 180},
        {"fieldname": "party",         "label": _("Kontragent"), "fieldtype": "Data",     "width": 220},
        {"fieldname": "summa",         "label": _("Summa"),      "fieldtype": "Currency", "width": 140},
        {"fieldname": "doc_name",      "label": _("Hujjat"),     "fieldtype": "Link",     "options": "Kassa", "width": 150},
    ]


def get_data(filters):
    source_account = filters.get("source_account")
    from_date      = filters.get("from_date")
    to_date        = filters.get("to_date")
    filter_cat     = filters.get("party_type")
    filter_party   = (filters.get("party") or "").strip().lower()

    opening = _get_opening_balance(source_account, from_date)

    params = {"from_date": from_date, "to_date": to_date}
    conditions = ["date >= %(from_date)s", "date <= %(to_date)s", "docstatus = 1"]

    if source_account:
        # Oddiy tranzaksiyalar source_account dan + Ko'chirishda source YOKI target
        conditions.append(
            "(source_account = %(source_account)s OR "
            "(oborot = 'Перемещение' AND target_account = %(source_account)s))"
        )
        params["source_account"] = source_account

    where = " AND ".join(conditions)

    rows = frappe.db.sql(f"""
        SELECT
            name, date, oborot, summa,
            source_account, target_account,
            party_type, expense_kontragent
        FROM `tabKassa`
        WHERE {where}
        ORDER BY date, creation
    """, params, as_dict=True)

    data = []
    expense_summaries = {}
    balance = opening

    for row in rows:
        is_transfer = (row.oborot == "Перемещение")

        if is_transfer:
            # source_account berilgan holda: source → chiqim, target → kirim
            if source_account:
                if row.source_account == source_account:
                    kirim, chiqim = 0, flt(row.summa)
                else:  # target_account == source_account
                    kirim, chiqim = flt(row.summa), 0
            else:
                # Global ko'rinish: ko'chirish balansga ta'sir qilmaydi (ichki harakat)
                kirim, chiqim = 0, 0
            direction = "Ko'chirish"
            category  = "Ko'chirish"
            party_display = " → ".join(filter(None, [row.source_account, row.target_account]))

        elif row.oborot == "Приход":
            kirim, chiqim = flt(row.summa), 0
            direction     = "Kirim"
            category      = row.party_type or "Boshqa"
            party_display = row.expense_kontragent or row.party_type or ""

        else:  # Расход
            kirim, chiqim = 0, flt(row.summa)
            direction     = "Chiqim"
            category      = row.party_type or "Boshqa"
            party_display = row.expense_kontragent or row.party_type or ""

        # Balansni har doim yangilash (filtrdan qat'iy nazar — haqiqiy qoldiq)
        balance += kirim - chiqim

        # Kategoriya filtri
        if filter_cat and category != filter_cat:
            continue

        # Kontragent filtri
        if filter_party and filter_party not in party_display.lower():
            continue

        # Xarajatlar breakdown (summary uchun)
        if category == "Xarajatlar" and chiqim:
            key = row.expense_kontragent or "Boshqa xarajatlar"
            bucket = expense_summaries.setdefault(key, {"kirim": 0, "chiqim": 0})
            bucket["kirim"]  += kirim
            bucket["chiqim"] += chiqim

        data.append({
            "date":           row.date,
            "source_account": row.source_account,
            "direction":      direction,
            "party_type":     category,
            "party":          party_display,
            "summa":          kirim if kirim else chiqim,
            "doc_name":       row.name,
            "_kirim":         kirim,
            "_chiqim":        chiqim,
            "_category":      category,
        })

    closing = balance
    return data, expense_summaries, opening, closing


def _get_opening_balance(source_account, from_date):
    params = {"from_date": from_date}
    if source_account:
        params["source_account"] = source_account
        result = frappe.db.sql("""
            SELECT COALESCE(
                SUM(CASE
                    WHEN oborot = 'Приход'      AND source_account = %(source_account)s THEN summa
                    WHEN oborot = 'Перемещение' AND target_account = %(source_account)s THEN summa
                    ELSE 0
                END) -
                SUM(CASE
                    WHEN oborot = 'Расход'      AND source_account = %(source_account)s THEN summa
                    WHEN oborot = 'Перемещение' AND source_account = %(source_account)s THEN summa
                    ELSE 0
                END), 0) AS balance
            FROM `tabKassa`
            WHERE date < %(from_date)s AND docstatus = 1
        """, params)
    else:
        # Global: ko'chirishlar ichki harakat — balansga ta'sir qilmaydi
        result = frappe.db.sql("""
            SELECT COALESCE(
                SUM(CASE WHEN oborot = 'Приход' THEN summa ELSE 0 END) -
                SUM(CASE WHEN oborot = 'Расход' THEN summa ELSE 0 END), 0) AS balance
            FROM `tabKassa`
            WHERE date < %(from_date)s AND docstatus = 1
        """, params)
    return flt(result[0][0]) if result else 0


def _fmt(val):
    """0 ni ham ko'rsatadi, None/None → '0.00'"""
    return f"{flt(val):,.2f}"


def get_summary_html(data, expense_summaries, opening, closing):
    """Data bo'sh bo'lsa ham opening/closing ko'rsatiladi."""

    # Kategoriya totallari
    totals = {}
    for row in data:
        cat = row.get("_category") or "Boshqa"
        b = totals.setdefault(cat, {"kirim": 0, "chiqim": 0})
        b["kirim"]  += flt(row.get("_kirim"))
        b["chiqim"] += flt(row.get("_chiqim"))

    # Xarajatlar subcategory qatorlari
    expense_sub_rows = ""
    if expense_summaries:
        for desc, t in expense_summaries.items():
            expense_sub_rows += f"""
            <tr class="dds-exp-sub" style="display:none;background:#fff8e1;">
                <td style="padding:7px 10px 7px 28px;border:1px solid #ddd;font-style:italic;">{escape(desc)}</td>
                <td style="padding:7px 10px;border:1px solid #ddd;text-align:right;color:#388e3c;">{_fmt(t['kirim'])}</td>
                <td style="padding:7px 10px;border:1px solid #ddd;text-align:right;color:#d32f2f;">{_fmt(t['chiqim'])}</td>
            </tr>"""

    if expense_summaries:
        exp_toggle = """onclick="(function(){
            var rows=document.querySelectorAll('.dds-exp-sub');
            var arr=document.getElementById('dds-exp-arr');
            var vis=rows.length&&rows[0].style.display!=='none';
            for(var i=0;i<rows.length;i++){rows[i].style.display=vis?'none':'table-row';}
            arr.innerHTML=vis?'&#9654;':'&#9660;';
        })()" style="cursor:pointer;" """
        exp_label = '<span id="dds-exp-arr" style="margin-right:5px;font-size:10px;">&#9654;</span>Xarajatlar'
    else:
        exp_toggle = ""
        exp_label  = "Xarajatlar"

    CATEGORIES = [
        ("Mijozlar",             "Mijozlar"),
        ("Yetkazib beruvchilar", "Yetkazib beruvchilar"),
        ("Xodimlar",             "Xodimlar"),
        ("Ko'chirish",           "Ko'chirish"),
        ("Boshqa",               "Boshqa"),
    ]

    detail_rows = ""
    for cat_key, cat_label in CATEGORIES:
        t = totals.get(cat_key, {"kirim": 0, "chiqim": 0})
        if not t["kirim"] and not t["chiqim"]:
            continue
        detail_rows += f"""
        <tr>
            <td style="padding:9px 10px;border:1px solid #ddd;">{cat_label}</td>
            <td style="padding:9px 10px;border:1px solid #ddd;text-align:right;color:#388e3c;">{_fmt(t['kirim'])}</td>
            <td style="padding:9px 10px;border:1px solid #ddd;text-align:right;color:#d32f2f;">{_fmt(t['chiqim'])}</td>
        </tr>"""

    exp_t = totals.get("Xarajatlar", {"kirim": 0, "chiqim": 0})
    if exp_t["kirim"] or exp_t["chiqim"] or expense_summaries:
        detail_rows += f"""
        <tr {exp_toggle}>
            <td style="padding:9px 10px;border:1px solid #ddd;">{exp_label}</td>
            <td style="padding:9px 10px;border:1px solid #ddd;text-align:right;color:#388e3c;">{_fmt(exp_t['kirim'])}</td>
            <td style="padding:9px 10px;border:1px solid #ddd;text-align:right;color:#d32f2f;">{_fmt(exp_t['chiqim'])}</td>
        </tr>
        {expense_sub_rows}"""

    return f"""
    <div style="margin-top:20px;padding:15px;background:#f9f9f9;border-radius:5px;">
        <table style="width:100%;border-collapse:collapse;background:white;">
            <thead>
                <tr style="background:#f0f0f0;">
                    <th style="padding:10px;text-align:left;border:1px solid #ddd;width:40%;"></th>
                    <th style="padding:10px;text-align:right;border:1px solid #ddd;width:30%;color:#388e3c;">Kirim</th>
                    <th style="padding:10px;text-align:right;border:1px solid #ddd;width:30%;color:#d32f2f;">Chiqim</th>
                </tr>
            </thead>
            <tbody>
                <tr style="background:#e3f2fd;">
                    <td style="padding:10px;border:1px solid #ddd;font-weight:bold;">Boshlang'ich qoldiq</td>
                    <td style="padding:10px;border:1px solid #ddd;text-align:right;font-weight:bold;"
                        colspan="2">{_fmt(opening)}</td>
                </tr>
                {detail_rows}
                <tr style="background:#e3f2fd;font-weight:bold;">
                    <td style="padding:12px;border:1px solid #ddd;font-weight:bold;">Oxirgi qoldiq</td>
                    <td style="padding:12px;border:1px solid #ddd;text-align:right;font-weight:bold;"
                        colspan="2">{_fmt(closing)}</td>
                </tr>
            </tbody>
        </table>
    </div>"""
