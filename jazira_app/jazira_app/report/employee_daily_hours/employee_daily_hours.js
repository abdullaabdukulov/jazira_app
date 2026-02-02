// Copyright (c) 2026, Jazira App
// License: MIT

frappe.query_reports["Employee Daily Hours"] = {
    "filters": [
        {
            "fieldname": "employee",
            "label": __("Employee"),
            "fieldtype": "Link",
            "options": "Employee",
            "reqd": 1,
            "get_query": function() {
                return { filters: { "status": "Active" } };
            }
        },
        {
            "fieldname": "date",
            "label": __("Date"),
            "fieldtype": "Date",
            "reqd": 1,
            "default": frappe.datetime.get_today()
        },
        {
            "fieldname": "show_raw_logs",
            "label": __("Show Raw Logs"),
            "fieldtype": "Check",
            "default": 0
        }
    ],

    "formatter": function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        // Status coloring
        if (column.fieldname === "status" && data && data.status) {
            if (data.status === "OK") {
                value = `<span style="color:green;font-weight:bold;">${value}</span>`;
            } else if (data.status.includes("Missing") || data.status === "Invalid order") {
                value = `<span style="color:red;font-weight:bold;">${value}</span>`;
            } else {
                value = `<span style="color:gray;">${value}</span>`;
            }
        }

        // Worked time coloring (green if >= 8 hours)
        if (column.fieldname === "worked" && data && data.worked && data.worked !== "-") {
            const parts = data.worked.split(":");
            const hours = parseInt(parts[0]) || 0;
            if (hours >= 8) {
                value = `<span style="color:green;font-weight:bold;">${value}</span>`;
            } else if (hours > 0) {
                value = `<span style="color:blue;">${value}</span>`;
            }
        }

        // Breaks coloring (orange if breaks exist)
        if (column.fieldname === "breaks" && data && data.breaks && data.breaks !== "-") {
            value = `<span style="color:orange;">${value}</span>`;
        }

        // Raw logs section header
        if (data && data.employee === "--- Raw Logs ---") {
            value = `<strong style="color:#333;">${value}</strong>`;
        }

        // Highlight break logs
        if (column.fieldname === "is_break" && data && data.is_break === "Yes") {
            value = `<span style="color:orange;font-weight:bold;">${value}</span>`;
        }

        // Color checkin_reason
        if (column.fieldname === "checkin_reason" && data && data.checkin_reason) {
            if (data.checkin_reason === "TEMP_OUT") {
                value = `<span style="color:orange;">${value}</span>`;
            } else if (data.checkin_reason === "RETURN") {
                value = `<span style="color:purple;">${value}</span>`;
            }
        }

        return value;
    }
};
