// Akt Sverka Report Filters

frappe.query_reports["Akt Sverka"] = {
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
            fieldname: "party_type",
            label: __("Kontragent turi"),
            fieldtype: "Link",
            options: "Party Type",
            default: "Supplier",
            reqd: 1,
            on_change: function() {
                frappe.query_report.set_filter_value("party", "");
            }
        },
        {
            fieldname: "party",
            label: __("Kontragent"),
            fieldtype: "Dynamic Link",
            options: "party_type",
            reqd: 1
        }
    ],
    
    formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        
        if (data) {
            // Boshlang'ich qoldiq - ko'k
            if (data.is_opening) {
                value = `<span style="color:#1890ff;font-weight:600;">${value}</span>`;
            }
            
            // Jami - sariq fon
            if (data.is_total) {
                value = `<span style="font-weight:700;background:#fff3cd;padding:2px 6px;">${value}</span>`;
            }
            
            // Manfiy qoldiq - qizil
            if (column.fieldname === "balance" && data.balance < 0) {
                value = `<span style="color:#f5222d;">${value}</span>`;
            }
        }
        
        return value;
    }
};