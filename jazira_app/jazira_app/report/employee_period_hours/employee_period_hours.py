# Copyright (c) 2026, Jazira App
# License: MIT
"""
Davriy Ish Vaqti Hisoboti (Employee Period Hours Report)

Xodimning tanlangan davr uchun kunlik ish vaqti va maosh hisoboti
"""

import frappe
from frappe import _
from frappe.utils import getdate, add_days, date_diff, flt
from datetime import datetime, timedelta, time as dt_time


def execute(filters=None):
    if not filters:
        filters = {}
    
    if not filters.get("employee"):
        frappe.throw(_("Xodimni tanlang"))
    if not filters.get("from_date"):
        frappe.throw(_("Boshlanish sanasini tanlang"))
    if not filters.get("to_date"):
        frappe.throw(_("Tugash sanasini tanlang"))
    
    columns = get_columns()
    data, report_summary, chart = get_data(filters)
    
    return columns, data, None, chart, report_summary


def get_columns():
    """Sodda ustunlar"""
    return [
        {
            "label": _("Sana"),
            "fieldname": "date",
            "fieldtype": "Date",
            "width": 100
        },
        {
            "label": _("Kun"),
            "fieldname": "day_name",
            "fieldtype": "Data",
            "width": 90
        },
        {
            "label": _("Keldi"),
            "fieldname": "first_in",
            "fieldtype": "Data",
            "width": 80
        },
        {
            "label": _("Ketdi"),
            "fieldname": "last_out",
            "fieldtype": "Data",
            "width": 80
        },
        {
            "label": _("Ishladi"),
            "fieldname": "worked",
            "fieldtype": "Data",
            "width": 80
        },
        {
            "label": _("Tanaffus"),
            "fieldname": "breaks",
            "fieldtype": "Data",
            "width": 80
        },
        {
            "label": _("Maosh"),
            "fieldname": "earnings",
            "fieldtype": "Currency",
            "width": 120
        },
        {
            "label": _("Holat"),
            "fieldname": "status",
            "fieldtype": "Data",
            "width": 120
        }
    ]


def get_data(filters):
    employee = filters.get("employee")
    from_date = getdate(filters.get("from_date"))
    to_date = getdate(filters.get("to_date"))
    
    # Validatsiya
    if from_date > to_date:
        frappe.throw(_("Boshlanish sanasi tugash sanasidan keyin bo'lishi mumkin emas"))
    
    if date_diff(to_date, from_date) > 62:
        frappe.throw(_("Maksimum 2 oy (62 kun) tanlash mumkin"))
    
    # Xodim ma'lumotlari
    emp = frappe.db.get_value(
        "Employee",
        employee,
        ["employee_name", "hourly_rate"],
        as_dict=True
    ) or {}
    
    employee_name = emp.get("employee_name") or employee
    hourly_rate = flt(emp.get("hourly_rate") or 0)
    
    # Loglarni olish
    search_start = datetime.combine(add_days(from_date, -1), dt_time(12, 0, 0))
    search_end = datetime.combine(add_days(to_date, 1), dt_time(12, 0, 0))
    
    logs = frappe.db.sql("""
        SELECT name, time, log_type, checkin_reason
        FROM `tabEmployee Checkin`
        WHERE employee = %s AND time >= %s AND time <= %s
        ORDER BY time ASC
    """, (employee, search_start, search_end), as_dict=True)
    
    # Kun nomlari
    day_names = {
        0: "Dushanba",
        1: "Seshanba", 
        2: "Chorshanba",
        3: "Payshanba",
        4: "Juma",
        5: "Shanba",
        6: "Yakshanba"
    }
    
    data = []
    total_worked = 0
    total_breaks = 0
    total_earnings = 0.0
    days_worked = 0
    days_total = 0
    
    # Chart uchun ma'lumotlar
    chart_labels = []
    chart_worked = []
    
    current_date = from_date
    while current_date <= to_date:
        days_total += 1
        day_result = calculate_day(logs, current_date)
        
        # Kun nomi
        day_name = day_names.get(current_date.weekday(), "")
        is_weekend = current_date.weekday() >= 5
        
        # Keldi vaqti
        first_in_str = "—"
        if day_result["first_in"]:
            first_in_str = day_result["first_in"].strftime("%H:%M")
        
        # Ketdi vaqti
        last_out_str = "—"
        if day_result["last_out"]:
            lo = day_result["last_out"]
            if lo.date() != current_date:
                last_out_str = lo.strftime("%d-%m %H:%M")
            else:
                last_out_str = lo.strftime("%H:%M")
        
        # Ishlagan vaqt
        worked_str = format_minutes(day_result["worked_minutes"])
        breaks_str = format_minutes(day_result["break_minutes"]) if day_result["break_minutes"] > 0 else "—"
        
        # Kunlik maosh
        worked_hours = day_result["worked_minutes"] / 60.0
        daily_earnings = worked_hours * hourly_rate
        
        # Holat
        status = get_status_display(day_result["status"], is_weekend)
        
        row = {
            "date": current_date,
            "day_name": day_name,
            "first_in": first_in_str,
            "last_out": last_out_str,
            "worked": worked_str if day_result["worked_minutes"] > 0 else "—",
            "breaks": breaks_str,
            "earnings": daily_earnings if daily_earnings > 0 else None,
            "status": status,
            "is_weekend": is_weekend,
            "worked_minutes": day_result["worked_minutes"]
        }
        
        data.append(row)
        
        # Jami hisob
        if day_result["worked_minutes"] > 0:
            total_worked += day_result["worked_minutes"]
            total_breaks += day_result["break_minutes"]
            total_earnings += daily_earnings
            days_worked += 1
        
        # Chart uchun
        chart_labels.append(current_date.strftime("%d"))
        chart_worked.append(round(day_result["worked_minutes"] / 60, 1))
        
        current_date = add_days(current_date, 1)
    
    # Bo'sh qator
    data.append({})
    
    # JAMI qatori
    data.append({
        "date": None,
        "day_name": "📊 JAMI:",
        "first_in": f"{days_worked} kun",
        "last_out": "",
        "worked": format_minutes(total_worked),
        "breaks": format_minutes(total_breaks) if total_breaks > 0 else "—",
        "earnings": total_earnings,
        "status": "",
        "is_total": True
    })
    
    # O'rtacha
    avg_worked = total_worked / days_worked if days_worked > 0 else 0
    avg_earnings = total_earnings / days_worked if days_worked > 0 else 0
    
    data.append({
        "date": None,
        "day_name": "📈 O'rtacha:",
        "first_in": "",
        "last_out": "",
        "worked": format_minutes(int(avg_worked)),
        "breaks": "",
        "earnings": avg_earnings if avg_earnings > 0 else None,
        "status": "/kun",
        "is_total": True
    })
    
    # Report summary (yuqorida ko'rinadi)
    report_summary = [
        {
            "label": _("Xodim"),
            "value": employee_name,
            "datatype": "Data",
            "indicator": "blue"
        },
        {
            "label": _("Davr"),
            "value": f"{from_date.strftime('%d-%m')} — {to_date.strftime('%d-%m-%Y')}",
            "datatype": "Data"
        },
        {
            "label": _("Ishlagan kunlar"),
            "value": f"{days_worked} / {days_total}",
            "datatype": "Data",
            "indicator": "green" if days_worked >= days_total * 0.8 else "orange"
        },
        {
            "label": _("Jami soat"),
            "value": format_minutes(total_worked),
            "datatype": "Data",
            "indicator": "blue"
        },
        {
            "label": _("Soatlik stavka"),
            "value": frappe.format_value(hourly_rate, {"fieldtype": "Currency"}),
            "datatype": "Data"
        },
        {
            "label": _("💰 JAMI MAOSH"),
            "value": total_earnings,
            "datatype": "Currency",
            "indicator": "green"
        }
    ]
    
    # Chart
    chart = {
        "data": {
            "labels": chart_labels,
            "datasets": [
                {
                    "name": _("Ishlagan soat"),
                    "values": chart_worked
                }
            ]
        },
        "type": "bar",
        "colors": ["#5e64ff"],
        "barOptions": {
            "spaceRatio": 0.3
        },
        "height": 200
    }
    
    return data, report_summary, chart


def calculate_day(all_logs, selected_date):
    """Kunlik ish vaqtini hisoblash"""
    
    next_day = add_days(selected_date, 1)
    
    result = {
        "first_in": None,
        "last_out": None,
        "worked_minutes": 0,
        "break_minutes": 0,
        "status": "NO_LOG"
    }
    
    # Bugungi loglar
    today_logs = [l for l in all_logs if l.time.date() == selected_date]
    
    # Ertangi ertalabki loglar (tungi smena uchun)
    next_early = [l for l in all_logs 
                  if l.time.date() == next_day 
                  and l.time.hour < 12]
    
    # IN loglar (RETURN emas)
    in_logs = [l for l in today_logs 
               if l.log_type == "IN" and l.checkin_reason != "RETURN"]
    
    # OUT loglar (TEMP_OUT emas)
    out_logs = [l for l in today_logs + next_early 
                if l.log_type == "OUT" and l.checkin_reason != "TEMP_OUT"]
    
    if not in_logs:
        if out_logs:
            result["last_out"] = out_logs[-1].time
            result["status"] = "MISSING_IN"
        return result
    
    # First IN
    result["first_in"] = min(in_logs, key=lambda x: x.time).time
    
    # Last OUT
    if out_logs:
        result["last_out"] = max(out_logs, key=lambda x: x.time).time
    
    # Ish vaqtini hisoblash
    if result["first_in"] and result["last_out"]:
        total_delta = result["last_out"] - result["first_in"]
        total_minutes = int(total_delta.total_seconds() / 60)
        
        # Tanaffuslarni hisoblash
        break_minutes = calculate_breaks(today_logs)
        result["break_minutes"] = break_minutes
        
        # Sof ish vaqti
        result["worked_minutes"] = max(0, total_minutes - break_minutes)
        result["status"] = "OK"
    elif result["first_in"] and not result["last_out"]:
        result["status"] = "MISSING_OUT"
    
    return result


def calculate_breaks(logs):
    """Tanaffus vaqtini hisoblash"""
    break_minutes = 0
    
    temp_outs = sorted(
        [l for l in logs if l.checkin_reason == "TEMP_OUT"],
        key=lambda x: x.time
    )
    returns = sorted(
        [l for l in logs if l.checkin_reason == "RETURN"],
        key=lambda x: x.time
    )
    
    used = set()
    for to in temp_outs:
        for i, ret in enumerate(returns):
            if i not in used and ret.time > to.time:
                delta = ret.time - to.time
                break_minutes += int(delta.total_seconds() / 60)
                used.add(i)
                break
    
    return break_minutes


def format_minutes(minutes):
    """Minutlarni HH:MM formatga"""
    if minutes <= 0:
        return "00:00"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


def get_status_display(status, is_weekend=False):
    """Holatni o'zbek tilida"""
    if status == "OK":
        return "✅ Normada"
    elif status == "MISSING_OUT":
        return "⚠️ Chiqmagan"
    elif status == "MISSING_IN":
        return "⚠️ Kelmagan"
    elif status == "NO_LOG":
        if is_weekend:
            return "🔵 Dam olish"
        return "⬜ Log yo'q"
    return status