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

	si.insert(ignore_permissions=True)
	si.submit()
	frappe.db.commit()
	return si


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
