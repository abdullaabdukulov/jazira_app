# Copyright (c) 2026, Jazira App
# License: MIT
"""
Employee Daily Hours Report

Calculates worked hours for ONE employee on ONE date using Employee Checkin logs.
Deducts break time when TEMP_OUT → RETURN pairs exist.

Logic:
- worked_time = (last_out - first_in) - sum(all_breaks)
- break = RETURN.time - TEMP_OUT.time (only when paired)
- unpaired TEMP_OUT or RETURN are ignored (not counted as breaks)
"""

import frappe
from frappe import _
from frappe.utils import getdate
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
        {"label": _("Last OUT"), "fieldname": "last_out", "fieldtype": "Data", "width": 80},
        {"label": _("Gross Time"), "fieldname": "gross_time", "fieldtype": "Data", "width": 100},
        {"label": _("Breaks"), "fieldname": "breaks", "fieldtype": "Data", "width": 80},
        {"label": _("Worked (HH:MM)"), "fieldname": "worked", "fieldtype": "Data", "width": 110},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
    ]
    
    if filters.get("show_raw_logs"):
        columns.extend([
            {"label": _(""), "fieldname": "spacer", "fieldtype": "Data", "width": 20},
            {"label": _("Log Time"), "fieldname": "log_time", "fieldtype": "Datetime", "width": 160},
            {"label": _("Log Type"), "fieldname": "log_type", "fieldtype": "Data", "width": 70},
            {"label": _("Reason"), "fieldname": "checkin_reason", "fieldtype": "Data", "width": 90},
            {"label": _("Device ID"), "fieldname": "device_id", "fieldtype": "Data", "width": 150},
            {"label": _("Break?"), "fieldname": "is_break", "fieldtype": "Data", "width": 70},
        ])
    
    return columns


def get_data(filters):
    """Fetch logs and calculate worked hours with break deduction."""
    employee = filters.get("employee")
    selected_date = getdate(filters.get("date"))
    show_raw_logs = filters.get("show_raw_logs")
    
    # Get employee name
    employee_name = frappe.db.get_value("Employee", employee, "employee_name") or ""
    
    # Build time window
    buffer_minutes = 15
    day_start = datetime.combine(selected_date, dt_time.min)
    day_end = datetime.combine(selected_date, dt_time.max)
    
    search_start = day_start - timedelta(minutes=buffer_minutes)
    search_end = day_end + timedelta(minutes=buffer_minutes)
    
    # Fetch all checkin logs with checkin_reason field
    logs = frappe.db.sql("""
        SELECT 
            name,
            employee,
            time,
            log_type,
            device_id,
            checkin_reason
        FROM `tabEmployee Checkin`
        WHERE employee = %s
          AND time >= %s
          AND time <= %s
        ORDER BY time ASC
    """, (employee, search_start, search_end), as_dict=True)
    
    # Filter to logs on selected date
    day_logs = [log for log in logs if day_start <= log.time <= day_end]
    
    # Separate by type
    # IN logs: log_type="IN" AND (checkin_reason is NULL or "IN" or "RETURN")
    # OUT logs: log_type="OUT" AND (checkin_reason is NULL or "OUT" or "TEMP_OUT")
    
    # For first IN: only real IN (not RETURN)
    real_in_logs = [
        log for log in day_logs 
        if log.log_type == "IN" and (not log.checkin_reason or log.checkin_reason == "IN")
    ]
    
    # For last OUT: only real OUT (not TEMP_OUT)
    real_out_logs = [
        log for log in day_logs 
        if log.log_type == "OUT" and (not log.checkin_reason or log.checkin_reason == "OUT")
    ]
    
    # TEMP_OUT and RETURN for break calculation
    temp_out_logs = [
        log for log in day_logs 
        if log.checkin_reason == "TEMP_OUT"
    ]
    
    return_logs = [
        log for log in day_logs 
        if log.checkin_reason == "RETURN"
    ]
    
    # Find first real IN and last real OUT
    first_in = min(real_in_logs, key=lambda x: x.time) if real_in_logs else None
    last_out = max(real_out_logs, key=lambda x: x.time) if real_out_logs else None
    
    # Calculate breaks (pair TEMP_OUT with next RETURN)
    breaks_info = calculate_breaks(temp_out_logs, return_logs)
    total_break_minutes = breaks_info["total_minutes"]
    paired_logs = breaks_info["paired_logs"]  # set of log names that are part of valid pairs
    
    # Calculate worked time
    gross_minutes = 0
    worked_minutes = 0
    status = "OK"
    
    if not day_logs:
        status = "No logs"
    elif not first_in and not last_out:
        # Maybe only TEMP_OUT/RETURN logs exist
        status = "No IN/OUT logs"
    elif not first_in:
        status = "Missing IN"
    elif not last_out:
        status = "Missing OUT"
    elif last_out.time <= first_in.time:
        status = "Invalid order"
    else:
        delta = last_out.time - first_in.time
        gross_minutes = int(delta.total_seconds() / 60)
        worked_minutes = gross_minutes - total_break_minutes
        if worked_minutes < 0:
            worked_minutes = 0
        status = "OK"
    
    # Format times
    def fmt_hhmm(minutes):
        h = minutes // 60
        m = minutes % 60
        return f"{h:02d}:{m:02d}"
    
    summary = {
        "employee": employee,
        "employee_name": employee_name,
        "date": selected_date,
        "first_in": first_in.time.strftime("%H:%M") if first_in else "-",
        "last_out": last_out.time.strftime("%H:%M") if last_out else "-",
        "gross_time": fmt_hhmm(gross_minutes) if gross_minutes > 0 else "-",
        "breaks": fmt_hhmm(total_break_minutes) if total_break_minutes > 0 else "-",
        "worked": fmt_hhmm(worked_minutes),
        "status": status
    }
    
    data = [summary]
    
    # Add raw logs if requested
    if show_raw_logs and day_logs:
        data.append({})
        data.append({"employee": "--- Raw Logs ---"})
        
        for log in day_logs:
            is_break = "Yes" if log.name in paired_logs else ""
            data.append({
                "log_time": log.time,
                "log_type": log.log_type,
                "checkin_reason": log.checkin_reason or "-",
                "device_id": log.device_id or "-",
                "is_break": is_break
            })
    
    return data


def calculate_breaks(temp_out_logs, return_logs):
    """
    Pair TEMP_OUT with following RETURN to calculate break time.
    
    Rules:
    - Each TEMP_OUT should be followed by a RETURN
    - TEMP_OUT without RETURN = ignored (not counted)
    - RETURN without preceding TEMP_OUT = ignored
    - Only valid pairs count as break time
    
    Returns:
        dict with total_minutes and set of paired log names
    """
    total_break_minutes = 0
    paired_logs = set()
    
    if not temp_out_logs or not return_logs:
        return {"total_minutes": 0, "paired_logs": set()}
    
    # Sort both lists by time
    temp_outs = sorted(temp_out_logs, key=lambda x: x.time)
    returns = sorted(return_logs, key=lambda x: x.time)
    
    # Match each TEMP_OUT with the next RETURN after it
    used_returns = set()
    
    for temp_out in temp_outs:
        # Find the first RETURN that comes after this TEMP_OUT and hasn't been used
        matching_return = None
        for ret in returns:
            if ret.name not in used_returns and ret.time > temp_out.time:
                matching_return = ret
                break
        
        if matching_return:
            # Valid pair found
            break_delta = matching_return.time - temp_out.time
            break_minutes = int(break_delta.total_seconds() / 60)
            total_break_minutes += break_minutes
            
            # Mark both logs as paired
            paired_logs.add(temp_out.name)
            paired_logs.add(matching_return.name)
            used_returns.add(matching_return.name)
    
    return {
        "total_minutes": total_break_minutes,
        "paired_logs": paired_logs
    }
