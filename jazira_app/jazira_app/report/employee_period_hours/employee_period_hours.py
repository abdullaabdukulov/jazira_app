# Copyright (c) 2026, Jazira App
# License: MIT
"""
Employee Period Hours Report - date range
"""

import frappe
from frappe import _
from frappe.utils import getdate, add_days, date_diff
from datetime import datetime, timedelta, time as dt_time


def execute(filters=None):
    if not filters:
        filters = {}
    
    if not filters.get("employee"):
        frappe.throw(_("Please select an Employee"))
    if not filters.get("from_date"):
        frappe.throw(_("Please select From Date"))
    if not filters.get("to_date"):
        frappe.throw(_("Please select To Date"))
    
    columns = get_columns()
    data = get_data(filters)
    
    return columns, data


def get_columns():
    return [
        {"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 100},
        {"label": _("Day"), "fieldname": "day", "fieldtype": "Data", "width": 80},
        {"label": _("First IN"), "fieldname": "first_in", "fieldtype": "Data", "width": 80},
        {"label": _("Last OUT"), "fieldname": "last_out", "fieldtype": "Data", "width": 100},
        {"label": _("Gross Time"), "fieldname": "gross_time", "fieldtype": "Data", "width": 100},
        {"label": _("Breaks"), "fieldname": "breaks", "fieldtype": "Data", "width": 80},
        {"label": _("Worked"), "fieldname": "worked", "fieldtype": "Data", "width": 100},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 150},
    ]


def get_data(filters):
    employee = filters.get("employee")
    from_date = getdate(filters.get("from_date"))
    to_date = getdate(filters.get("to_date"))
    
    if from_date > to_date:
        frappe.throw(_("From Date cannot be after To Date"))
    
    if date_diff(to_date, from_date) > 31:
        frappe.throw(_("Date range cannot exceed 31 days"))
    
    # Fetch all logs
    search_start = datetime.combine(add_days(from_date, -1), dt_time(12, 0, 0))
    search_end = datetime.combine(add_days(to_date, 1), dt_time(12, 0, 0))
    
    logs = frappe.db.sql("""
        SELECT name, employee, time, log_type, checkin_reason
        FROM `tabEmployee Checkin`
        WHERE employee = %s AND time >= %s AND time <= %s
        ORDER BY time ASC
    """, (employee, search_start, search_end), as_dict=True)
    
    day_names = {
        0: "Dush", 1: "Sesh", 2: "Chor", 3: "Pay", 4: "Jum", 5: "Shan", 6: "Yak"
    }
    
    data = []
    total_worked = 0
    total_breaks = 0
    total_gross = 0
    days_worked = 0
    
    current_date = from_date
    while current_date <= to_date:
        day_result = calculate_day(logs, current_date)
        
        def fmt_hhmm(minutes):
            if minutes <= 0:
                return "-"
            h = minutes // 60
            m = minutes % 60
            return f"{h:02d}:{m:02d}"
        
        # Format first_in
        first_in_str = "-"
        if day_result["first_in"]:
            fi = day_result["first_in"]
            if isinstance(fi, datetime):
                first_in_str = fi.strftime("%H:%M")
            else:
                first_in_str = fi.strftime("%H:%M")
        
        # Format last_out
        last_out_str = "-"
        if day_result["last_out"]:
            lo = day_result["last_out"]
            if isinstance(lo, datetime):
                if lo.date() != current_date:
                    last_out_str = lo.strftime("%d-%m %H:%M")
                else:
                    last_out_str = lo.strftime("%H:%M")
            else:
                last_out_str = lo.strftime("%H:%M")
        
        row = {
            "date": current_date,
            "day": day_names.get(current_date.weekday(), ""),
            "first_in": first_in_str,
            "last_out": last_out_str,
            "gross_time": fmt_hhmm(day_result["gross_minutes"]),
            "breaks": fmt_hhmm(day_result["break_minutes"]),
            "worked": fmt_hhmm(day_result["worked_minutes"]),
            "status": day_result["status"]
        }
        
        data.append(row)
        
        if day_result["worked_minutes"] > 0:
            total_worked += day_result["worked_minutes"]
            total_gross += day_result["gross_minutes"]
            total_breaks += day_result["break_minutes"]
            days_worked += 1
        
        current_date = add_days(current_date, 1)
    
    # Empty row
    data.append({})
    
    # Totals
    def fmt_total(minutes):
        if minutes <= 0:
            return "00:00"
        h = minutes // 60
        m = minutes % 60
        return f"{h:02d}:{m:02d}"
    
    data.append({
        "date": "JAMI:",
        "day": f"{days_worked} kun",
        "gross_time": fmt_total(total_gross),
        "breaks": fmt_total(total_breaks),
        "worked": fmt_total(total_worked),
    })
    
    return data


def calculate_day(all_logs, selected_date):
    worked_minutes = 0
    gross_minutes = 0
    break_minutes = 0
    
    first_in = None
    last_out = None
    status = "OK"
    
    prev_day = add_days(selected_date, -1)
    next_day = add_days(selected_date, 1)
    
    # Previous day INs
    prev_day_ins = [l for l in all_logs if l.log_type == "IN" 
                   and l.time.date() == prev_day and l.time.hour >= 12
                   and l.checkin_reason != "RETURN"]
    
    # Today's INs
    today_ins = [l for l in all_logs if l.log_type == "IN" 
                and l.time.date() == selected_date
                and l.checkin_reason != "RETURN"]
    
    # Today's OUTs
    today_outs = [l for l in all_logs if l.log_type == "OUT" 
                 and l.time.date() == selected_date
                 and l.checkin_reason != "TEMP_OUT"]
    
    # TEMP_OUT/RETURN
    temp_out_logs = [l for l in all_logs if l.checkin_reason == "TEMP_OUT" 
                    and l.time.date() == selected_date]
    return_logs = [l for l in all_logs if l.checkin_reason == "RETURN" 
                  and l.time.date() == selected_date]
    
    # Next day early OUTs
    next_day_early_outs = [l for l in all_logs if l.log_type == "OUT" 
                          and l.time.date() == next_day 
                          and l.time.hour < 12
                          and l.checkin_reason != "TEMP_OUT"]
    
    # Case 1: No IN
    if not today_ins:
        if today_outs:
            earliest_out = min(today_outs, key=lambda x: x.time)
            if prev_day_ins:
                status = f"Oldingi kun ({prev_day.strftime('%d-%m')})"
            else:
                status = "Missing IN"
            last_out = earliest_out.time
        else:
            status = "-"
        
        return {
            "worked_minutes": 0,
            "gross_minutes": 0,
            "break_minutes": 0,
            "first_in": None,
            "last_out": last_out,
            "status": status
        }
    
    # Case 2: INs exist
    first_in = min(today_ins, key=lambda x: x.time).time  # datetime
    
    available_outs = sorted(today_outs + next_day_early_outs, key=lambda x: x.time)
    
    current_in = None
    used_outs = set()
    
    for log in sorted(today_ins + available_outs, key=lambda x: x.time):
        if log.log_type == "IN" and log.time.date() == selected_date and log.checkin_reason != "RETURN":
            current_in = log
            
        elif log.log_type == "OUT" and current_in and log.name not in used_outs and log.checkin_reason != "TEMP_OUT":
            delta = log.time - current_in.time
            minutes = int(delta.total_seconds() / 60)
            
            if minutes > 0:
                worked_minutes += minutes
                last_out = log.time  # datetime
                used_outs.add(log.name)
            
            current_in = None
    
    if current_in:
        status = "Missing OUT"
    
    # Gross Time
    if first_in and last_out:
        if isinstance(first_in, datetime) and isinstance(last_out, datetime):
            gross_minutes = int((last_out - first_in).total_seconds() / 60)
        else:
            # Convert to datetime if needed
            if isinstance(first_in, datetime):
                fi_dt = first_in
            else:
                fi_dt = datetime.combine(selected_date, first_in)
            
            if isinstance(last_out, datetime):
                lo_dt = last_out
            else:
                lo_dt = datetime.combine(selected_date, last_out)
                if lo_dt < fi_dt:
                    lo_dt = datetime.combine(next_day, last_out)
            
            gross_minutes = int((lo_dt - fi_dt).total_seconds() / 60)
    
    # Breaks
    break_minutes = calculate_breaks(temp_out_logs, return_logs)
    
    return {
        "worked_minutes": worked_minutes,
        "gross_minutes": gross_minutes,
        "break_minutes": break_minutes,
        "first_in": first_in,
        "last_out": last_out,
        "status": status
    }


def calculate_breaks(temp_out_logs, return_logs):
    if not temp_out_logs or not return_logs:
        return 0
    
    total = 0
    temp_outs = sorted(temp_out_logs, key=lambda x: x.time)
    returns = sorted(return_logs, key=lambda x: x.time)
    used = set()
    
    for to in temp_outs:
        for ret in returns:
            if ret.name not in used and ret.time > to.time:
                delta = ret.time - to.time
                total += int(delta.total_seconds() / 60)
                used.add(ret.name)
                break
    
    return total