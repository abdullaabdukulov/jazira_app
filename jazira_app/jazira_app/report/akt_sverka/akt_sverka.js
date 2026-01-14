// Copyright (c) 2024, Jazira App and contributors
// For license information, please see license.txt

frappe.query_reports["Akt Sverka"] = {
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
            options: "Customer\nSupplier\nEmployee\nShareholder",
            default: "Customer",
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
            reqd: 1,
            get_query: function() {
                let party_type = frappe.query_report.get_filter_value("party_type");
                if (party_type === "Customer") {
                    return { filters: { disabled: 0 } };
                } else if (party_type === "Supplier") {
                    return { filters: { disabled: 0 } };
                }
                return {};
            }
        },
        {
            fieldname: "account",
            label: __("Hisob"),
            fieldtype: "Link",
            options: "Account",
            get_query: function() {
                return {
                    filters: {
                        company: frappe.query_report.get_filter_value("company"),
                        account_type: ["in", ["Receivable", "Payable"]],
                        is_group: 0
                    }
                };
            }
        }
    ],
    
    formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        
        if (data) {
            // Opening/Closing rows bold
            if (data.is_opening || data.is_closing) {
                value = "<b>" + value + "</b>";
            }
            
            // Negative balance in red
            if (column.fieldname === "balance" && data.balance < 0) {
                value = "<span style='color:red'>" + value + "</span>";
            }
        }
        
        return value;
    },
    
    onload: function(report) {
        report.page.add_inner_button(__("PDF yuklab olish"), function() {
            frappe.query_report.export_report("PDF");
        });
    }
};
