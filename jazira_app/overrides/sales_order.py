import frappe


def on_validate(doc, method=None):
	"""
	Inter-company SO draft holatida ustama foizni itemlarga qo'shish.
	Har safar PO dan original narxni olib hisoblanadi — markup ustiga markup qo'shilmaydi.
	"""
	if not doc.inter_company_order_reference:
		return

	branch_company = frappe.db.get_value("Customer", doc.customer, "represents_company")
	if not branch_company:
		return

	markup_percent = _get_markup_percent(branch_company)
	if not markup_percent:
		return

	# PO dan original narxlarni olish (har safar PO bazasidan hisoblash uchun)
	po_rates = {
		row.item_code: row.rate
		for row in frappe.get_all(
			"Purchase Order Item",
			filters={"parent": doc.inter_company_order_reference},
			fields=["item_code", "rate"],
		)
	}

	multiplier = 1 + (markup_percent / 100)
	for item in doc.items:
		original_rate = po_rates.get(item.item_code, item.rate)
		item.rate = round(original_rate * multiplier, 2)
		item.amount = round(item.rate * item.qty, 2)

	doc.run_method("calculate_taxes_and_totals")


def on_submit(doc, method=None):
	"""
	Inter-company Sales Order submit bo'lganda avtomatik:
	  1. Sales Invoice yaratadi (Sklad kompaniyasi uchun)
	  2. Purchase Invoice yaratadi (Branch kompaniyasi uchun)
	"""
	if not doc.inter_company_order_reference:
		return

	try:
		# PO dan branch warehouse ni olish
		po_warehouse = frappe.db.get_value(
			"Purchase Order", doc.inter_company_order_reference, "set_warehouse"
		)
		si = _create_sales_invoice(doc)
		pi = _create_purchase_invoice(si, po_warehouse)

		frappe.msgprint(
			f"Sales Invoice <b>{si.name}</b> va Purchase Invoice <b>{pi.name}</b> avtomatik yaratildi",
			alert=True,
			indicator="green",
		)

	except Exception:
		frappe.log_error(frappe.get_traceback(), "Inter Company Invoice Auto Create")
		frappe.msgprint(
			"Invoice avtomatik yaratishda xato. Loglarni tekshiring.",
			indicator="orange",
		)


def _create_sales_invoice(so_doc):
	from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

	si = make_sales_invoice(so_doc.name, ignore_permissions=True)
	si.flags.ignore_permissions = True
	si.flags.ignore_mandatory = True
	si.order_type = None
	si.update_stock = 1

	# Sklad omboridan chiqim — SO dagi set_warehouse ishlatiladi
	if so_doc.set_warehouse:
		si.set_warehouse = so_doc.set_warehouse

	_apply_markup(si)

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

	# Avval kompaniya bo'yicha maxsus foiz qidiramiz
	for row in settings.company_markups:
		if row.company == company:
			return row.percent

	# Topilmasa default foiz
	return settings.default_markup_percent or 0


def _apply_markup(si):
	"""SI itemlari narxiga ustama foiz qo'shish (SO da allaqachon qo'shilgan, qayta qo'shilmaydi)."""
	# SO validate da markup qo'shilgan — SI ham SO dan keladi, shuning uchun narxlar tayyor.
	# calculate_taxes_and_totals ni qayta ishga tushirish yetarli.
	si.run_method("calculate_taxes_and_totals")


def _create_purchase_invoice(si_doc, branch_warehouse=None):
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import (
		make_inter_company_purchase_invoice,
	)

	pi = make_inter_company_purchase_invoice(si_doc.name)
	pi.flags.ignore_permissions = True
	pi.update_stock = 1

	# Branch omboriga kirim — PO dan kelgan warehouse
	if branch_warehouse:
		pi.set_warehouse = branch_warehouse
		for item in pi.items:
			item.warehouse = branch_warehouse

	pi.insert(ignore_permissions=True)
	pi.submit()
	frappe.db.commit()
	return pi
