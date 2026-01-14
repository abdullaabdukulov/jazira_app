// Copyright (c) 2024, Jazira App and contributors
// For license information, please see license.txt

frappe.query_reports["DDS Report"] = {
    filters: [
        {
            fieldname: "from_date",
            label: __("Boshlanish sanasi"),
            fieldtype: "Date",
            default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
            reqd: 1
        },
        {
            fieldname: "to_date",
            label: __("Tugash sanasi"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            reqd: 1
        },
        {
            fieldname: "source_account",
            label: __("Kassa hisobi"),
            fieldtype: "Link",
            options: "Mode of Payment"
        }
    ]
};
