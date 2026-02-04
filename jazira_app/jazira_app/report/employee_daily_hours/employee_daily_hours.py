# Copyright (c) 2026, Jazira App
# License: MIT
"""
Employee Daily Hours Report

Calculates worked hours based on "Every Valid Check-in and Check-out" method.
Supports NIGHT SHIFTS - if IN is on day D and OUT is on day D+1, it still counts.

Example (night shift):
  Day 1: 12:32 IN
  Day 2: 02:02 OUT
  = 13 soat 30 minut ish (bir sessiya)
"""

import frappe
from frappe import _
from frappe.utils import getdate, add_days
from datetime import datetime, timedelta, time as dt_time


def execute(filters=None):
    """Main entry point for Script Report."""
    if not filters:
        filters = {}
    
    if not filters.get("employee"):
        frappe.throw(_("Please select an Employee"))
    if not filters.get("date"):
        frappe.throw(_("Please select a Date"))
    
    columns = get_columns(filters)
    data = get_data(filters)
    
    return columns, data


def get_columns(filters):
    """Define report columns."""
    columns = [
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 140},
        {"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 150},
        {"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 100},
        {"label": _("First IN"), "fieldname": "first_in", "fieldtype": "Data", "width": 80},
        {"label": _("Last OUT"), "fieldname": "last_out", "fieldtype": "Data", "width": 100},
        {"label": _("Worked (HH:MM)"), "fieldname": "worked", "fieldtype": "Data", "width": 110},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
    ]
    
    if filters.get("show_raw_logs"):
        columns.extend([
            {"label": _(""), "fieldname": "spacer", "fieldtype": "Data", "width": 20},
            {"label": _("Log Time"), "fieldname": "log_time", "fieldtype": "Datetime", "width": 160},
            {"label": _("Log Type"), "fieldname": "log_type", "fieldtype": "Data", "width": 70},
            {"label": _("Paired With"), "fieldname": "paired_with", "fieldtype": "Data", "width": 160},
            {"label": _("Duration"), "fieldname": "duration", "fieldtype": "Data", "width": 80},
        ])
    
    return columns


def get_data(filters):
    """Fetch logs and calculate worked hours."""
    employee = filters.get("employee")
    selected_date = getdate(filters.get("date"))
    show_raw_logs = filters.get("show_raw_logs")
    
    # Get employee name
    employee_name = frappe.db.get_value("Employee", employee, "employee_name") or ""
    
    # Time window: selected day 00:00 to NEXT day 12:00 (for night shifts)
    day_start = datetime.combine(selected_date, dt_time.min)
    day_end = datetime.combine(selected_date, dt_time.max)
    
    # Extend search to next day noon (for night shift OUT)
    next_day = add_days(selected_date, 1)
    search_end = datetime.combine(next_day, dt_time(12, 0, 0))  # Next day 12:00
    
    # Also check previous day for IN (if viewing the OUT day)
    prev_day = add_days(selected_date, -1)
    search_start = datetime.combine(prev_day, dt_time(12, 0, 0))  # Previous day 12:00
    
    # Fetch all checkin logs in extended window
    logs = frappe.db.sql("""
        SELECT 
            name,
            employee,
            time,
            log_type,
            device_id
        FROM `tabEmployee Checkin`
        WHERE employee = %s
          AND time >= %s
          AND time <= %s
        ORDER BY time ASC
    """, (employee, search_start, search_end), as_dict=True)
    
    if not logs:
        return [{
            "employee": employee,
            "employee_name": employee_name,
            "date": selected_date,
            "first_in": "-",
            "last_out": "-",
            "worked": "00:00",
            "status": "No logs"
        }]
    
    # Find work sessions that START on the selected date
    result = calculate_work_sessions(logs, day_start, day_end)
    
    # Format output
    def fmt_hhmm(minutes):
        if minutes <= 0:
            return "00:00"
        h = minutes // 60
        m = minutes % 60
        return f"{h:02d}:{m:02d}"
    
    # Determine status
    status = "OK"
    if result["worked_minutes"] == 0:
        if result["has_in"] and not result["has_out"]:
            status = "Missing OUT"
        elif result["has_out"] and not result["has_in"]:
            status = "Missing IN"
        else:
            status = "No valid pairs"
    elif result["has_in"] and not result["has_out"]:
        status = "Missing OUT"
    
    # Format last_out with date if it's next day
    last_out_str = "-"
    if result["last_out"]:
        out_time = result["last_out"]
        if out_time.date() != selected_date:
            # Show date for next day
            last_out_str = out_time.strftime("%d-%m %H:%M")
        else:
            last_out_str = out_time.strftime("%H:%M")
    
    summary = {
        "employee": employee,
        "employee_name": employee_name,
        "date": selected_date,
        "first_in": result["first_in"].strftime("%H:%M") if result["first_in"] else "-",
        "last_out": last_out_str,
        "worked": fmt_hhmm(result["worked_minutes"]),
        "status": status
    }
    
    data = [summary]
    
    # Add raw logs
    if show_raw_logs and result["session_logs"]:
        data.append({})
        data.append({"employee": "--- Raw Logs ---"})
        
        for log in result["session_logs"]:
            pair_info = result["log_pairs"].get(log.name, {})
            paired_time = pair_info.get("paired_time")
            if paired_time and isinstance(paired_time, datetime):
                if paired_time.date() != selected_date:
                    paired_str = paired_time.strftime("%d-%m %H:%M")
                else:
                    paired_str = paired_time.strftime("%H:%M")
            else:
                paired_str = pair_info.get("paired_with", "-")
            
            data.append({
                "log_time": log.time,
                "log_type": log.log_type,
                "paired_with": paired_str,
                "duration": pair_info.get("duration", "-"),
            })
    
    return data


def calculate_work_sessions(logs, day_start, day_end):
    """
    Calculate work sessions starting on the selected date.
    
    Logic:
    1. Find all IN logs on the selected date
    2. For each IN, find the next OUT (even if on next day)
    3. Sum all valid IN→OUT durations
    """
    worked_minutes = 0
    log_pairs = {}
    session_logs = []
    
    first_in = None
    last_out = None
    has_in = False
    has_out = False
    
    # Get INs that start on selected date
    day_in_logs = [l for l in logs if l.log_type == "IN" and day_start <= l.time <= day_end]
    
    if not day_in_logs:
        # No IN on this day - check if there's an OUT (might be viewing wrong day)
        day_out_logs = [l for l in logs if l.log_type == "OUT" and day_start <= l.time <= day_end]
        if day_out_logs:
            has_out = True
            last_out = max(day_out_logs, key=lambda x: x.time).time
        return {
            "worked_minutes": 0,
            "first_in": None,
            "last_out": last_out,
            "has_in": False,
            "has_out": has_out,
            "log_pairs": {},
            "session_logs": day_out_logs
        }
    
    has_in = True
    first_in = min(day_in_logs, key=lambda x: x.time).time
    
    # Process each IN and find its matching OUT
    current_in = None
    
    for log in logs:
        # Only process if log is on or after selected date start
        if log.time < day_start:
            continue
            
        if log.log_type == "IN":
            # Only consider INs on the selected date
            if log.time <= day_end:
                current_in = log
                session_logs.append(log)
            
        elif log.log_type == "OUT":
            if current_in:
                # Valid pair found
                delta = log.time - current_in.time
                minutes = int(delta.total_seconds() / 60)
                
                if minutes > 0:
                    worked_minutes += minutes
                    has_out = True
                    last_out = log.time
                    
                    # Store pair info
                    log_pairs[current_in.name] = {
                        "paired_time": log.time,
                        "paired_with": log.time.strftime("%H:%M"),
                        "duration": f"{minutes // 60}:{minutes % 60:02d}"
                    }
                    log_pairs[log.name] = {
                        "paired_time": current_in.time,
                        "paired_with": current_in.time.strftime("%H:%M"),
                        "duration": f"{minutes // 60}:{minutes % 60:02d}"
                    }
                    
                    session_logs.append(log)
                
                current_in = None
    
    # Handle unpaired IN
    if current_in:
        log_pairs[current_in.name] = {
            "paired_with": "No OUT",
            "duration": "-"
        }
    
    return {
        "worked_minutes": worked_minutes,
        "first_in": first_in,
        "last_out": last_out,
        "has_in": has_in,
        "has_out": has_out,
        "log_pairs": log_pairs,
        "session_logs": session_logs
    }