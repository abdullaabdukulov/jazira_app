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
		si = _create_sales_invoice(doc)
		pi = _create_purchase_invoice(si)

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

	_apply_markup(si)

	si.insert(ignore_permissions=True)
	si.submit()
	frappe.db.commit()
	return si


def _get_markup_percent(company):
	"""Sklad Settings dan kompaniya uchun ustama foizni olish."""
	settings = frappe.get_cached_doc("Sklad Settings")

	# Avval kompaniya bo'yicha maxsus foiz qidiramiz
	for row in settings.company_markups:
		if row.company == company:
			return row.percent

	# Topilmasa default foiz
	return settings.default_markup_percent or 0


def _apply_markup(si):
	"""SI itemlari narxiga ustama foiz qo'shish."""
	# SO customer -> represents_company -> branch company
	branch_company = frappe.db.get_value("Customer", si.customer, "represents_company")
	if not branch_company:
		return

	markup_percent = _get_markup_percent(branch_company)
	if not markup_percent:
		return

	multiplier = 1 + (markup_percent / 100)
	for item in si.items:
		item.rate = round(item.rate * multiplier, 2)
		item.amount = round(item.rate * item.qty, 2)

	si.run_method("calculate_taxes_and_totals")


def _create_purchase_invoice(si_doc):
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import (
		make_inter_company_purchase_invoice,
	)

	pi = make_inter_company_purchase_invoice(si_doc.name)
	pi.flags.ignore_permissions = True
	pi.insert(ignore_permissions=True)
	pi.submit()
	frappe.db.commit()
	return pi
