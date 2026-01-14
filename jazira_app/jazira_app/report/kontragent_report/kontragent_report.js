// Copyright (c) 2024, Jazira App and contributors
// For license information, please see license.txt

frappe.query_reports["Kontragent Report"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            reqd: 1
        },
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
            fieldtype: "Select",
            options: "\nCustomer\nSupplier\nEmployee\nShareholder\nРасходы\nПрочее лицо"
        },
        {
            fieldname: "party",
            label: __("Kontragent"),
            fieldtype: "Dynamic Link",
            options: "party_type",
            get_query: function() {
                let party_type = frappe.query_report.get_filter_value("party_type");
                if (!party_type) return {};
                
                if (party_type === "Customer") {
                    return { filters: { disabled: 0 } };
                } else if (party_type === "Supplier") {
                    return { filters: { disabled: 0 } };
                } else if (party_type === "Прочее лицо") {
                    return { 
                        doctype: "Kassa Kontragent",
                        filters: { is_active: 1 } 
                    };
                } else if (party_type === "Расходы") {
                    return { 
                        doctype: "Account",
                        filters: { 
                            company: frappe.query_report.get_filter_value("company"),
                            root_type: "Expense",
                            is_group: 0
                        } 
                    };
                }
                return {};
            }
        },
        {
            fieldname: "include_expenses",
            label: __("Xarajatlarni ko'rsatish (Расходы)"),
            fieldtype: "Check",
            default: 1
        },
        {
            fieldname: "include_prochie_litsa",
            label: __("Boshqa shaxslarni ko'rsatish (Прочее лицо)"),
            fieldtype: "Check",
            default: 1
        },
        {
            fieldname: "show_zero_balance",
            label: __("Nol qoldiqlarni ko'rsatish"),
            fieldtype: "Check",
            default: 0
        }
    ],
    
    formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        
        if (data) {
            // Group header styling
            if (data.is_group_header) {
                value = "<b style='color:#5e64ff;font-size:13px'>" + value + "</b>";
            }
            
            // Subtotal styling
            if (data.is_subtotal) {
                value = "<b style='background-color:#e8f4fd'>" + value + "</b>";
            }
            
            // Grand total styling
            if (data.is_grand_total) {
                value = "<b style='background-color:#d4edda;font-size:13px'>" + value + "</b>";
            }
            
            // Negative balance in red
            if (column.fieldname === "closing_balance" && data.closing_balance < 0) {
                value = "<span style='color:red'>" + value + "</span>";
            }
            
            // Positive balance in green (for receivables)
            if (column.fieldname === "closing_balance" && data.closing_balance > 0 && 
                (data.party_type === "Customer" || data.party_type === "Прочее лицо")) {
                value = "<span style='color:green'>" + value + "</span>";
            }
            
            // Expense styling
            if (data.party_type === "Расходы") {
                if (column.fieldname === "party_type") {
                    value = "<span style='color:#dc3545'>" + value + "</span>";
                }
            }
            
            // Prochie Litsa styling
            if (data.party_type === "Прочее лицо") {
                if (column.fieldname === "party_type") {
                    value = "<span style='color:#6f42c1'>" + value + "</span>";
                }
            }
        }
        
        return value;
    },
    
    onload: function(report) {
        report.page.add_inner_button(__("Akt Sverka"), function() {
            let party_type = frappe.query_report.get_filter_value("party_type");
            let party = frappe.query_report.get_filter_value("party");
            
            if (!party_type || !party) {
                frappe.msgprint(__("Akt Sverka uchun kontragent turini va kontragentni tanlang"));
                return;
            }
            
            // Only standard party types can go to Akt Sverka
            if (!["Customer", "Supplier", "Employee", "Shareholder"].includes(party_type)) {
                frappe.msgprint(__("Akt Sverka faqat Customer, Supplier, Employee, Shareholder uchun mavjud"));
                return;
            }
            
            frappe.set_route("query-report", "Akt Sverka", {
                company: frappe.query_report.get_filter_value("company"),
                from_date: frappe.query_report.get_filter_value("from_date"),
                to_date: frappe.query_report.get_filter_value("to_date"),
                party_type: party_type,
                party: party
            });
        });
    }
};
