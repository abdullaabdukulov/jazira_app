# Copyright (c) 2026, Jazira App
# License: MIT
"""
Kunlik Ish Vaqti Hisoboti (Employee Daily Hours Report)

Sodda va tushunarli format:
- Keldi/Ketdi vaqtlari
- Ish vaqti (soat:minut)
- Tanaffus vaqti
- Kunlik daromad
"""

import frappe
from frappe import _
from frappe.utils import getdate, flt
from datetime import datetime, timedelta, time as dt_time


def execute(filters=None):
    if not filters:
        filters = {}
    
    if not filters.get("employee"):
        frappe.throw(_("Xodimni tanlang"))
    if not filters.get("date"):
        frappe.throw(_("Sanani tanlang"))
    
    columns = get_columns()
    data = get_data(filters)
    
    return columns, data


def get_columns():
    """Keng ustunlar - biznes uchun qulay"""
    return [
        {
            "label": _("#"),
            "fieldname": "row_num",
            "fieldtype": "Data",
            "width": 60
        },
        {
            "label": _("Vaqt / Sarlavha"),
            "fieldname": "time",
            "fieldtype": "Data",
            "width": 150
        },
        {
            "label": _("Qiymat / Turi"),
            "fieldname": "log_type",
            "fieldtype": "Data",
            "width": 200
        },
        {
            "label": _("Izoh / Qo'shimcha"),
            "fieldname": "description",
            "fieldtype": "Data",
            "width": 280
        },
        {
            "label": _("Davomiylik"),
            "fieldname": "duration",
            "fieldtype": "Data",
            "width": 120
        }
    ]


def get_data(filters):
    employee = filters.get("employee")
    selected_date = getdate(filters.get("date"))
    
    # Xodim ma'lumotlari (designation va company qo'shildi)
    emp = frappe.db.get_value(
        "Employee",
        employee,
        ["employee_name", "hourly_rate", "designation", "company"],
        as_dict=True
    ) or {}
    
    employee_name = emp.get("employee_name") or employee
    hourly_rate = flt(emp.get("hourly_rate") or 0)
    designation = emp.get("designation") or ""
    company = emp.get("company") or ""
    
    # Loglarni olish (bugun va ertangi kun ertalab)
    logs = get_employee_logs(employee, selected_date)
    
    data = []
    
    # ═══════════════════════════════════════════════════════════════
    # SARLAVHA - ism, lavozim, filial alohida qatorlarda
    # ═══════════════════════════════════════════════════════════════
    data.append({
        "row_num": "👤",
        "time": "XODIM:",
        "log_type": employee_name,
        "description": f"📅 Sana: {selected_date.strftime('%d-%m-%Y')}",
        "duration": ""
    })
    
    # Lavozim qatori
    if designation:
        data.append({
            "row_num": "",
            "time": "💼 Lavozim:",
            "log_type": designation,
            "description": "",
            "duration": ""
        })
    
    # Filial qatori
    if company:
        data.append({
            "row_num": "",
            "time": "🏢 Filial:",
            "log_type": company,
            "description": "",
            "duration": ""
        })
    
    data.append({})  # Bo'sh qator
    
    if not logs:
        # Log yo'q
        data.append({
            "row_num": "⚠️",
            "time": "",
            "log_type": "LOG YO'Q",
            "description": "Bu sana uchun hech qanday kirish/chiqish qayd etilmagan",
            "duration": ""
        })
        return data
    
    # ═══════════════════════════════════════════════════════════════
    # HISOB-KITOB
    # ═══════════════════════════════════════════════════════════════
    result = calculate_work_time(logs, selected_date)
    
    # KELDI vaqti
    first_in_str = result["first_in"].strftime("%H:%M") if result["first_in"] else "—"
    
    # KETDI vaqti
    if result["last_out"]:
        if result["last_out"].date() != selected_date:
            last_out_str = result["last_out"].strftime("%d-%m %H:%M")
        else:
            last_out_str = result["last_out"].strftime("%H:%M")
    else:
        last_out_str = "—"
    
    # Ish vaqti
    worked_str = format_minutes(result["worked_minutes"])
    
    # Tanaffus
    break_str = format_minutes(result["break_minutes"]) if result["break_minutes"] > 0 else "—"
    
    # Daromad
    worked_hours = result["worked_minutes"] / 60.0
    earnings = worked_hours * hourly_rate
    
    # ═══════════════════════════════════════════════════════════════
    # XULOSA QATORI
    # ═══════════════════════════════════════════════════════════════
    data.append({
        "row_num": "📊",
        "time": "XULOSA",
        "log_type": "",
        "description": "",
        "duration": ""
    })
    
    data.append({
        "row_num": "",
        "time": "🟢 Keldi",
        "log_type": first_in_str,
        "description": f"🔴 Ketdi: {last_out_str}",
        "duration": ""
    })
    
    data.append({
        "row_num": "",
        "time": "⏱️ Ish vaqti",
        "log_type": worked_str,
        "description": f"☕ Tanaffus: {break_str}",
        "duration": ""
    })
    
    if hourly_rate > 0:
        data.append({
            "row_num": "",
            "time": "💰 Daromad",
            "log_type": f"{earnings:,.0f} UZS",
            "description": f"Stavka: {hourly_rate:,.0f} UZS/soat",
            "duration": ""
        })
    
    # Status
    status_icon = "✅" if result["status"] == "OK" else "⚠️"
    status_text = get_status_text(result["status"])
    data.append({
        "row_num": "",
        "time": f"{status_icon} Holat",
        "log_type": status_text,
        "description": "",
        "duration": ""
    })
    
    data.append({})  # Bo'sh qator
    
    # ═══════════════════════════════════════════════════════════════
    # LOGLAR RO'YXATI
    # ═══════════════════════════════════════════════════════════════
    data.append({
        "row_num": "📋",
        "time": "LOGLAR",
        "log_type": f"({len(result['logs'])} ta)",
        "description": "",
        "duration": ""
    })
    
    data.append({
        "row_num": "#",
        "time": "Vaqt",
        "log_type": "Turi",
        "description": "Izoh",
        "duration": ""
    })
    
    prev_time = None
    for i, log in enumerate(result["logs"], 1):
        log_time = log["time"]
        
        # Vaqt formati
        if log_time.date() != selected_date:
            time_str = log_time.strftime("%d-%m %H:%M")
        else:
            time_str = log_time.strftime("%H:%M")
        
        # Turi va rang
        log_type_display = get_log_type_display(log["type"], log["reason"])
        
        # Izoh
        description = get_log_description(log["type"], log["reason"])
        
        # Davomiylik (oldingi logdan)
        duration_str = ""
        if prev_time and log["type"] in ["OUT", "TEMP_OUT"]:
            delta = log_time - prev_time
            minutes = int(delta.total_seconds() / 60)
            if minutes > 0:
                duration_str = format_minutes(minutes)
        
        data.append({
            "row_num": str(i),
            "time": time_str,
            "log_type": log_type_display,
            "description": description,
            "duration": duration_str
        })
        
        prev_time = log_time
    
    return data


def get_employee_logs(employee, selected_date):
    """Xodim loglarini olish (bugun + ertangi kun ertalab)"""
    from frappe.utils import add_days
    
    next_day = add_days(selected_date, 1)
    
    # Bugungi barcha loglar + ertangi kun 12:00 gacha
    day_start = datetime.combine(selected_date, dt_time.min)
    search_end = datetime.combine(next_day, dt_time(12, 0, 0))
    
    logs = frappe.db.sql("""
        SELECT name, time, log_type, checkin_reason
        FROM `tabEmployee Checkin`
        WHERE employee = %s 
          AND time >= %s 
          AND time <= %s
        ORDER BY time ASC
    """, (employee, day_start, search_end), as_dict=True)
    
    return logs


def calculate_work_time(logs, selected_date):
    """Ish vaqtini hisoblash"""
    from frappe.utils import add_days
    
    next_day = add_days(selected_date, 1)
    
    result = {
        "first_in": None,
        "last_out": None,
        "worked_minutes": 0,
        "break_minutes": 0,
        "status": "OK",
        "logs": []
    }
    
    # Loglarni qayta ishlash
    processed_logs = []
    for log in logs:
        log_type = log.log_type
        reason = log.checkin_reason or log_type
        
        processed_logs.append({
            "time": log.time,
            "type": log_type,
            "reason": reason
        })
    
    result["logs"] = processed_logs
    
    if not processed_logs:
        result["status"] = "NO_LOGS"
        return result
    
    # First IN (RETURN emas)
    in_logs = [l for l in processed_logs if l["type"] == "IN" and l["reason"] != "RETURN"]
    if in_logs:
        result["first_in"] = in_logs[0]["time"]
    
    # Last OUT (TEMP_OUT emas)
    out_logs = [l for l in processed_logs if l["type"] == "OUT" and l["reason"] != "TEMP_OUT"]
    if out_logs:
        result["last_out"] = out_logs[-1]["time"]
    
    # Ish vaqtini hisoblash (First IN to Last OUT)
    if result["first_in"] and result["last_out"]:
        total_delta = result["last_out"] - result["first_in"]
        total_minutes = int(total_delta.total_seconds() / 60)
        
        # Tanaffuslarni hisoblash
        break_minutes = calculate_breaks(processed_logs)
        result["break_minutes"] = break_minutes
        
        # Sof ish vaqti = Jami - Tanaffus
        result["worked_minutes"] = max(0, total_minutes - break_minutes)
    elif result["first_in"] and not result["last_out"]:
        result["status"] = "MISSING_OUT"
    elif not result["first_in"]:
        result["status"] = "MISSING_IN"
    
    return result


def calculate_breaks(logs):
    """Tanaffus vaqtini hisoblash (TEMP_OUT dan RETURN gacha)"""
    break_minutes = 0
    
    temp_outs = [l for l in logs if l["reason"] == "TEMP_OUT"]
    returns = [l for l in logs if l["reason"] == "RETURN"]
    
    used_returns = set()
    
    for to in temp_outs:
        for i, ret in enumerate(returns):
            if i not in used_returns and ret["time"] > to["time"]:
                delta = ret["time"] - to["time"]
                break_minutes += int(delta.total_seconds() / 60)
                used_returns.add(i)
                break
    
    return break_minutes


def format_minutes(minutes):
    """Minutlarni HH:MM formatga o'girish"""
    if minutes <= 0:
        return "00:00"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


def get_log_type_display(log_type, reason):
    """Log turini chiroyli ko'rsatish"""
    if reason == "TEMP_OUT":
        return "🟠 CHIQDI (tanaffus)"
    elif reason == "RETURN":
        return "🟣 QAYTDI"
    elif log_type == "IN":
        return "🟢 KELDI"
    elif log_type == "OUT":
        return "🔴 KETDI"
    return log_type


def get_log_description(log_type, reason):
    """Log uchun izoh"""
    if reason == "TEMP_OUT":
        return "Tanaffusga chiqdi"
    elif reason == "RETURN":
        return "Tanaffusdan qaytdi"
    elif log_type == "IN" and reason == "IN":
        return "Ishga keldi"
    elif log_type == "OUT" and reason == "OUT":
        return "Ishdan ketdi"
    return ""


def get_status_text(status):
    """Status matnini o'zbek tilida"""
    status_map = {
        "OK": "Normada ✓",
        "MISSING_OUT": "Chiqish vaqti qayd etilmagan",
        "MISSING_IN": "Kirish vaqti qayd etilmagan",
        "NO_LOGS": "Log yo'q"
    }
    return status_map.get(status, status)