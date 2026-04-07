// Copyright (c) 2024, Jazira App and contributors
// For license information, please see license.txt

frappe.query_reports["DDS Report"] = {
    "filters": [
        {
            "fieldname": "from_date",
            "label": __("Sana dan"),
            "fieldtype": "Date",
            "default": frappe.datetime.add_months(frappe.datetime.get_today(), -1),
            "reqd": 1
        },
        {
            "fieldname": "to_date",
            "label": __("Sana gacha"),
            "fieldtype": "Date",
            "default": frappe.datetime.get_today(),
            "reqd": 1
        },
        {
            "fieldname": "source_account",
            "label": __("Kassa hisobi"),
            "fieldtype": "Link",
            "options": "Mode of Payment"
        },
        {
            "fieldname": "party_type",
            "label": __("Kategoriya"),
            "fieldtype": "Select",
            "options": "\nMijozlar\nYetkazib beruvchilar\nXodimlar\nXarajatlar\nKo'chirish",
            "on_change": function() {
                frappe.query_report.set_filter_value("party", "");
            }
        },
        {
            "fieldname": "party",
            "label": __("Kontragent"),
            "fieldtype": "Data"
        }
    ],

    "formatter": function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (column.fieldname === "summa" && data) {
            if (data.direction === "Kirim") {
                value = `<span style="color:#1b5e20;font-weight:600;">${value}</span>`;
            } else if (data.direction === "Chiqim") {
                value = `<span style="color:#b71c1c;font-weight:600;">${value}</span>`;
            }
        }

        if (column.fieldname === "direction" && data) {
            if (data.direction === "Kirim") {
                value = `<span style="color:#1b5e20;font-weight:600;">▲ Kirim</span>`;
            } else if (data.direction === "Chiqim") {
                value = `<span style="color:#b71c1c;font-weight:600;">▼ Chiqim</span>`;
            } else if (data.direction === "Ko'chirish") {
                value = `<span style="color:#1565c0;font-weight:600;">↔ Ko'chirish</span>`;
            }
        }

        return value;
    }
};
