# Copyright (c) 2026, Jazira App
# License: MIT
"""
Employee Daily Hours Report

Shows summary + all logs (IN, OUT, TEMP_OUT, RETURN)
Calculates Gross Time, Breaks, and Worked time
"""

import frappe
from frappe import _
from frappe.utils import getdate, add_days
from datetime import datetime, timedelta, time as dt_time


def execute(filters=None):
    if not filters:
        filters = {}
    
    if not filters.get("employee"):
        frappe.throw(_("Please select an Employee"))
    if not filters.get("date"):
        frappe.throw(_("Please select a Date"))
    
    columns = get_columns()
    data = get_data(filters)
    
    return columns, data


def get_columns():
    return [
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 140},
        {"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 150},
        {"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 100},
        {"label": _("First IN"), "fieldname": "first_in", "fieldtype": "Data", "width": 80},
        {"label": _("Last OUT"), "fieldname": "last_out", "fieldtype": "Data", "width": 100},
        {"label": _("Gross Time"), "fieldname": "gross_time", "fieldtype": "Data", "width": 100},
        {"label": _("Breaks"), "fieldname": "breaks", "fieldtype": "Data", "width": 80},
        {"label": _("Worked (HH:MM)"), "fieldname": "worked", "fieldtype": "Data", "width": 110},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 180},
    ]


def get_data(filters):
    employee = filters.get("employee")
    selected_date = getdate(filters.get("date"))
    
    employee_name = frappe.db.get_value("Employee", employee, "employee_name") or ""
    
    # Time boundaries
    day_start = datetime.combine(selected_date, dt_time.min)
    day_end = datetime.combine(selected_date, dt_time.max)
    
    prev_day = add_days(selected_date, -1)
    next_day = add_days(selected_date, 1)
    
    search_start = datetime.combine(prev_day, dt_time(12, 0, 0))
    search_end = datetime.combine(next_day, dt_time(12, 0, 0))
    
    # Fetch logs with checkin_reason
    logs = frappe.db.sql("""
        SELECT name, employee, time, log_type, checkin_reason
        FROM `tabEmployee Checkin`
        WHERE employee = %s AND time >= %s AND time <= %s
        ORDER BY time ASC
    """, (employee, search_start, search_end), as_dict=True)
    
    if not logs:
        return [{
            "employee": employee,
            "employee_name": employee_name,
            "date": selected_date,
            "first_in": "-",
            "last_out": "-",
            "gross_time": "-",
            "breaks": "-",
            "worked": "00:00",
            "status": "No logs"
        }]
    
    # Calculate
    result = calculate_work_for_date(logs, selected_date, day_start, day_end)
    
    def fmt_hhmm(minutes):
        if minutes <= 0:
            return "00:00"
        h = minutes // 60
        m = minutes % 60
        return f"{h:02d}:{m:02d}"
    
    last_out_str = "-"
    if result["last_out"]:
        out_time = result["last_out"]
        if out_time.date() != selected_date:
            last_out_str = out_time.strftime("%d-%m %H:%M")
        else:
            last_out_str = out_time.strftime("%H:%M")
    
    # Summary row
    data = [{
        "employee": employee,
        "employee_name": employee_name,
        "date": selected_date,
        "first_in": result["first_in"].strftime("%H:%M") if result["first_in"] else "-",
        "last_out": last_out_str,
        "gross_time": fmt_hhmm(result["gross_minutes"]) if result["gross_minutes"] > 0 else "-",
        "breaks": fmt_hhmm(result["break_minutes"]) if result["break_minutes"] > 0 else "-",
        "worked": fmt_hhmm(result["worked_minutes"]),
        "status": result["status"]
    }]
    
    # Empty row separator
    data.append({})
    
    # Logs header
    data.append({
        "employee": "📋 Loglar:",
        "date": "#",
        "first_in": "Vaqt",
        "last_out": "Turi",
    })
    
    # All logs
    for i, log in enumerate(result["session_logs"], 1):
        log_date = log.time.date()
        if log_date != selected_date:
            time_str = log.time.strftime("%d-%m %H:%M:%S")
        else:
            time_str = log.time.strftime("%H:%M:%S")
        
        # Determine display type
        if log.checkin_reason in ["TEMP_OUT", "RETURN"]:
            log_type_display = log.checkin_reason
        else:
            log_type_display = log.log_type
        
        data.append({
            "date": i,
            "first_in": time_str,
            "last_out": log_type_display,
        })
    
    return data


def calculate_work_for_date(logs, selected_date, day_start, day_end):
    worked_minutes = 0
    gross_minutes = 0
    break_minutes = 0
    session_logs = []
    
    first_in = None
    last_out = None
    status = "OK"
    
    prev_day = add_days(selected_date, -1)
    next_day = add_days(selected_date, 1)
    
    # Previous day INs (after 12:00)
    prev_day_ins = [l for l in logs if l.log_type == "IN" 
                   and l.time.date() == prev_day and l.time.hour >= 12]
    
    # Today's logs - only real IN (not RETURN)
    today_ins = [l for l in logs if l.log_type == "IN" 
                and l.time.date() == selected_date
                and l.checkin_reason != "RETURN"]
    
    # Today's OUTs - only real OUT (not TEMP_OUT)
    today_outs = [l for l in logs if l.log_type == "OUT" 
                 and l.time.date() == selected_date
                 and l.checkin_reason != "TEMP_OUT"]
    
    # All logs on selected date (for display)
    today_all_logs = [l for l in logs if l.time.date() == selected_date]
    
    # TEMP_OUT and RETURN for break calculation
    temp_out_logs = [l for l in logs if l.checkin_reason == "TEMP_OUT" 
                    and l.time.date() == selected_date]
    return_logs = [l for l in logs if l.checkin_reason == "RETURN" 
                  and l.time.date() == selected_date]
    
    # Next day early OUTs (real OUT only)
    next_day_early_outs = [l for l in logs if l.log_type == "OUT" 
                          and l.time.date() == next_day 
                          and l.time.hour < 12
                          and l.checkin_reason != "TEMP_OUT"]
    
    # Next day early logs (for display)
    next_day_early_logs = [l for l in logs if l.time.date() == next_day and l.time.hour < 12]
    
    # Case 1: No real IN on selected date
    if not today_ins:
        if today_all_logs:
            if today_outs:
                earliest_out = min(today_outs, key=lambda x: x.time)
                if prev_day_ins:
                    status = f"Oldingi kun smenasi ({prev_day.strftime('%d-%m')})"
                else:
                    status = "Missing IN"
                last_out = earliest_out.time
            else:
                status = "No IN/OUT logs"
            session_logs = today_all_logs
        else:
            status = "No logs"
        
        return {
            "worked_minutes": 0,
            "gross_minutes": 0,
            "break_minutes": 0,
            "first_in": None,
            "last_out": last_out,
            "status": status,
            "session_logs": session_logs
        }
    
    # Case 2: Real INs exist on selected date
    first_in = min(today_ins, key=lambda x: x.time).time
    
    # All available real OUTs for pairing
    available_outs = sorted(today_outs + next_day_early_outs, key=lambda x: x.time)
    
    current_in = None
    used_outs = set()
    
    # Process only real IN/OUT for work calculation
    for log in sorted(today_ins + available_outs, key=lambda x: x.time):
        if log.log_type == "IN" and log.time.date() == selected_date and log.checkin_reason != "RETURN":
            current_in = log
            
        elif log.log_type == "OUT" and current_in and log.name not in used_outs and log.checkin_reason != "TEMP_OUT":
            delta = log.time - current_in.time
            minutes = int(delta.total_seconds() / 60)
            
            if minutes > 0:
                worked_minutes += minutes
                last_out = log.time
                used_outs.add(log.name)
            
            current_in = None
    
    if current_in:
        status = "Missing OUT"
    
    # Calculate Gross Time (first IN to last OUT)
    if first_in and last_out:
        first_in_dt = datetime.combine(selected_date, first_in)
        if last_out.date() != selected_date:
            last_out_dt = datetime.combine(last_out.date(), last_out.time())
        else:
            last_out_dt = datetime.combine(selected_date, last_out.time())
        
        if isinstance(last_out, datetime):
            gross_minutes = int((last_out - first_in_dt).total_seconds() / 60)
        else:
            gross_minutes = int((last_out_dt - first_in_dt).total_seconds() / 60)
    
    # Calculate Breaks (TEMP_OUT → RETURN pairs)
    break_minutes = calculate_breaks(temp_out_logs, return_logs)
    
    # Worked = Gross - Breaks (alternative calculation if needed)
    # But we already calculated worked_minutes from IN/OUT pairs
    
    # Session logs = today's logs + next day early logs (for display)
    session_logs = sorted(today_all_logs + next_day_early_logs, key=lambda x: x.time)
    
    return {
        "worked_minutes": worked_minutes,
        "gross_minutes": gross_minutes,
        "break_minutes": break_minutes,
        "first_in": first_in,
        "last_out": last_out,
        "status": status,
        "session_logs": session_logs
    }


def calculate_breaks(temp_out_logs, return_logs):
    """Calculate total break time from TEMP_OUT → RETURN pairs."""
    if not temp_out_logs or not return_logs:
        return 0
    
    total_break_minutes = 0
    temp_outs = sorted(temp_out_logs, key=lambda x: x.time)
    returns = sorted(return_logs, key=lambda x: x.time)
    
    used_returns = set()
    
    for temp_out in temp_outs:
        for ret in returns:
            if ret.name not in used_returns and ret.time > temp_out.time:
                break_delta = ret.time - temp_out.time
                total_break_minutes += int(break_delta.total_seconds() / 60)
                used_returns.add(ret.name)
                break
    
    return total_break_minutes