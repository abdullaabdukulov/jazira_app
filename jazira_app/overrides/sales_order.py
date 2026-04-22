import frappe


def on_submit(doc, method=None):
    """
    Inter-company Sales Order submit bo'lganda avtomatik:
      1. Sales Invoice yaratadi (Sklad kompaniyasi uchun)
      2. Purchase Invoice yaratadi (Branch kompaniyasi uchun)
    """
    if not doc.inter_company_order_reference:
        return

    try:
        # PO dan branch warehouse ni olish (header → items fallback)
        branch_warehouse = _get_po_warehouse(doc.inter_company_order_reference)
        si = _create_sales_invoice(doc)
        pi = _create_purchase_invoice(si, branch_warehouse)

        frappe.msgprint(
            f"Sales Invoice <b>{si.name}</b> va Purchase Invoice <b>{pi.name}</b> avtomatik yaratildi",
            alert=True,
            indicator="green",
        )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Inter Company Invoice Auto Create")
        frappe.msgprint(
            "Invoice avtomatik yaratishda xato. Error Log ni tekshiring.",
            indicator="orange",
        )


def _get_po_warehouse(po_name):
    """PO ning branch warehouse ni qaytaradi. Header → items fallback."""
    warehouse = frappe.db.get_value("Purchase Order", po_name, "set_warehouse")
    if warehouse:
        return warehouse
    # Header da yo'q bo'lsa birinchi itemdan olish
    return frappe.db.get_value(
        "Purchase Order Item",
        {"parent": po_name},
        "warehouse",
        order_by="idx asc",
    )


def _create_sales_invoice(so_doc):
    from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

    si = make_sales_invoice(so_doc.name, ignore_permissions=True)
    si.flags.ignore_permissions = True
    si.flags.ignore_mandatory = True
    si.order_type = None
    si.update_stock = 1

    # Sklad omboridan chiqim
    sklad_warehouse = so_doc.set_warehouse or _get_sklad_main_warehouse()
    if sklad_warehouse:
        si.set_warehouse = sklad_warehouse
        # Item darajasida ham belgilash (update_stock=1 uchun majburiy)
        for item in si.items:
            if not item.warehouse:
                item.warehouse = sklad_warehouse

    si.posting_date = so_doc.transaction_date
    si.due_date = so_doc.transaction_date

    si.run_method("calculate_taxes_and_totals")
    si.insert(ignore_permissions=True)
    si.submit()
    frappe.db.commit()
    return si


def _get_markup_percent(company):
    """Sklad Settings dan kompaniya uchun ustama foizni olish."""
    settings_name = frappe.db.get_all("Sklad Settings", limit=1, pluck="name")
    if not settings_name:
        frappe.throw("Sklad Settings topilmadi. Avval sozlang.")
    settings = frappe.get_doc("Sklad Settings", settings_name[0])

    for row in settings.company_markups:
        if row.company == company:
            return row.percent

    return settings.default_markup_percent or 0


def _get_sklad_main_warehouse():
    """Sklad Settings dan asosiy omborni qaytaradi."""
    names = frappe.db.get_all("Sklad Settings", limit=1, pluck="name")
    if not names:
        return None
    return frappe.db.get_value("Sklad Settings", names[0], "main_warehouse")


def _create_purchase_invoice(si_doc, branch_warehouse=None):
    from erpnext.accounts.doctype.sales_invoice.sales_invoice import (
        make_inter_company_purchase_invoice,
    )

    pi = make_inter_company_purchase_invoice(si_doc.name)
    pi.flags.ignore_permissions = True
    pi.update_stock = 1

    # Branch omboriga kirim
    if branch_warehouse:
        pi.set_warehouse = branch_warehouse
        for item in pi.items:
            item.warehouse = branch_warehouse
    else:
        # branch_warehouse topilmasa item darajasida bo'sh qolmasin
        missing = [item.item_code for item in pi.items if not item.warehouse]
        if missing:
            frappe.throw(
                f"Purchase Invoice uchun warehouse topilmadi. "
                f"Purchase Order da 'Set Warehouse' ni belgilang."
            )

    # update_stock=1 da expense_account inventory account bo'lishi kerak
    # Aks holda ERPNext "Expense Head Changed" warning beradi
    inventory_account = frappe.db.get_value(
        "Company", pi.company, "default_inventory_account"
    )
    if inventory_account:
        for item in pi.items:
            item.expense_account = inventory_account

    pi.posting_date = si_doc.posting_date
    pi.due_date = si_doc.posting_date

    pi.insert(ignore_permissions=True)
    pi.run_method("calculate_taxes_and_totals")
    pi.submit()
    frappe.db.commit()
    return pi
