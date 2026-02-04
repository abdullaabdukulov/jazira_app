// Copyright (c) 2026, Jazira App
// License: MIT

frappe.query_reports["Employee Period Hours"] = {
    "filters": [
        {
            "fieldname": "employee",
            "label": __("Employee"),
            "fieldtype": "Link",
            "options": "Employee",
            "reqd": 1
        },
        {
            "fieldname": "from_date",
            "label": __("From Date"),
            "fieldtype": "Date",
            "reqd": 1,
            "default": frappe.datetime.month_start()
        },
        {
            "fieldname": "to_date",
            "label": __("To Date"),
            "fieldtype": "Date",
            "reqd": 1,
            "default": frappe.datetime.get_today()
        }
    ],

    "formatter": function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (!data) return value;

        // Status coloring
        if (column.fieldname === "status") {
            if (data.status === "OK") {
                value = `<span style="color:green;font-weight:bold;">${value}</span>`;
            } else if (data.status === "Missing OUT" || data.status === "Missing IN") {
                value = `<span style="color:red;font-weight:bold;">${value}</span>`;
            } else if (data.status === "-") {
                value = `<span style="color:gray;">${value}</span>`;
            } else if (data.status && data.status.includes("Oldingi")) {
                value = `<span style="color:orange;">${value}</span>`;
            }
        }

        // Worked time coloring
        if (column.fieldname === "worked" && data.worked && data.worked !== "-") {
            const parts = data.worked.split(":");
            const hours = parseInt(parts[0]) || 0;
            if (hours >= 8) {
                value = `<span style="color:green;font-weight:bold;">${value}</span>`;
            } else if (hours > 0) {
                value = `<span style="color:blue;">${value}</span>`;
            }
        }

        // Breaks coloring
        if (column.fieldname === "breaks" && data.breaks && data.breaks !== "-") {
            value = `<span style="color:orange;">${value}</span>`;
        }

        // Total row styling
        if (data.date === "JAMI:") {
            value = `<strong>${value}</strong>`;
        }

        return value;
    }
};
