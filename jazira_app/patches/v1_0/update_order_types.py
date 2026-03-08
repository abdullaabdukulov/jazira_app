# -*- coding: utf-8 -*-
# Copyright (c) 2026, Jazira App
# License: MIT

"""
Patch: POS Invoice order_type variantlarini yangilash
======================================================

URY app standart order_type variantlarini (Dine In, Phone In, Take Away,
Delivery, Aggregators) Jazira uchun mos variantlar bilan almashtirish:

    Zal        — ichkarida ovqatlanish (Dine In)
    Saboy      — mijoz o'zi olib ketadi (Take Away)
    Dastavka   — yetkazib berish (Delivery)
    Dastavka Saboy — yetkazib berish + olib ketish
"""

import frappe


ORDER_TYPE_OPTIONS = "\nShu yerda\nSaboy\nDastavka\nDastavka Saboy"


def execute():
    for doctype in ("POS Invoice", "Sales Invoice"):
        cf_name = doctype + "-order_type"
        if not frappe.db.exists("Custom Field", cf_name):
            continue

        # Property Setter mavjud bo'lsa yangilash, bo'lmasa yaratish
        ps_name = doctype + "-order_type-options"
        if frappe.db.exists("Property Setter", ps_name):
            frappe.db.set_value("Property Setter", ps_name, "value", ORDER_TYPE_OPTIONS)
        else:
            frappe.make_property_setter({
                "doctype_or_field": "DocField",
                "doc_type": doctype,
                "field_name": "order_type",
                "property": "options",
                "value": ORDER_TYPE_OPTIONS,
                "property_type": "Text",
            })

        # Custom Field ning o'zini ham yangilash (UI'da to'g'ri ko'rinishi uchun)
        frappe.db.set_value("Custom Field", cf_name, "options", ORDER_TYPE_OPTIONS)

    frappe.db.commit()
    print("  [OK]  order_type variantlari yangilandi: Shu yerda, Saboy, Dastavka, Dastavka Saboy")
