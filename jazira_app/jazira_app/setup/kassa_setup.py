# -*- coding: utf-8 -*-
# Copyright (c) 2026, Jazira App
# License: MIT

"""
Kassa Module Setup - Party Type'larni yaratish
===============================================

Ishlatish:
    bench --site [site] execute jazira_app.jazira_app.setup.kassa_setup.create_party_types
"""

import frappe


def create_party_types():
    """Kassa uchun yangi Party Type'lar yaratish."""
    party_types = [
        {"party_type": "Расходы", "account_type": "Payable"}
    ]
    
    for pt in party_types:
        try:
            if not frappe.db.exists("Party Type", pt["party_type"]):
                doc = frappe.new_doc("Party Type")
                doc.party_type = pt["party_type"]
                doc.account_type = pt["account_type"]
                doc.flags.ignore_links = True
                doc.insert(ignore_permissions=True)
                frappe.db.commit()
                print(f"✅ Created Party Type: {pt['party_type']}")
            else:
                print(f"⏭️  Party Type already exists: {pt['party_type']}")
        except Exception as e:
            print(f"⚠️  Error creating {pt['party_type']}: {str(e)}")
    
    print("\n✅ Party Types setup completed!")


def create_sample_filials():
    """Namuna filiallar yaratish."""
    filials = ["Административ", "База", "Filial 1"]
    
    for name in filials:
        try:
            if not frappe.db.exists("Kassa Filial", name):
                doc = frappe.new_doc("Kassa Filial")
                doc.filial_name = name
                doc.is_active = 1
                doc.insert(ignore_permissions=True)
                frappe.db.commit()
                print(f"✅ Created Kassa Filial: {name}")
            else:
                print(f"⏭️  Kassa Filial already exists: {name}")
        except Exception as e:
            print(f"⚠️  Error creating {name}: {str(e)}")


def run_full_setup():
    """To'liq setup."""
    print("=" * 50)
    print("KASSA MODULE SETUP")
    print("=" * 50)
    
    print("\n1. Creating Party Types...")
    create_party_types()
    
    print("\n2. Creating Sample Filials...")
    create_sample_filials()

    print("\n" + "=" * 50)
    print("✅ SETUP COMPLETED!")
    print("=" * 50)


def ensure_payment_entry_kassa_field():
    """Payment Entry'ga "Kassa" Link maydonini qo'shadi va eskilarni to'ldiradi.

    Kassa to'lov yaratganda PE'ning reference_no'siga kassa nomini yozardi —
    lekin bu oddiy matn, bosib o'tib bo'lmasdi. Link maydoni bilan PE
    formasidan to'g'ridan-to'g'ri Kassa hujjatiga o'tiladi, Kassa'ning
    "Connections" bo'limida esa to'lovlari ko'rinadi.
    """
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    existed = frappe.db.exists(
        "Custom Field", {"dt": "Payment Entry", "fieldname": "custom_kassa"})

    create_custom_fields({
        "Payment Entry": [{
            "fieldname": "custom_kassa",
            "label": "Kassa",
            "fieldtype": "Link",
            "options": "Kassa",
            "insert_after": "reference_no",
            "read_only": 1,
            # Kassa amend/duplicate bo'lganda eski havola ko'chib qolmasin
            "no_copy": 1,
            "print_hide": 1,
            "in_standard_filter": 1,
            "description": "Ushbu to'lovni yaratgan Kassa hujjati",
        }]
    })
    if not existed:
        print("✅ Payment Entry.custom_kassa maydoni yaratildi")

    _backfill_payment_entry_kassa()


def _backfill_payment_entry_kassa():
    """Eski to'lovlarga Kassa havolasini kiritadi (idempotent).

    Manba — Kassa hujjatining o'z link maydonlari (payment_entry,
    payment_entry_receive, payment_entry_supplier): reference_no'dan ko'ra
    ishonchli, chunki uni foydalanuvchi o'zgartira olgan.
    """
    pairs = frappe.db.sql(
        """
        SELECT k.name AS kassa, pe.name AS pe
        FROM `tabKassa` k
        JOIN `tabPayment Entry` pe
          ON pe.name IN (k.payment_entry, k.payment_entry_receive, k.payment_entry_supplier)
        WHERE IFNULL(pe.custom_kassa, '') = ''
        """,
        as_dict=True,
    )
    for row in pairs:
        frappe.db.set_value(
            "Payment Entry", row.pe, "custom_kassa", row.kassa,
            update_modified=False)
    if pairs:
        print(f"✅ {len(pairs)} ta eski Payment Entry'ga Kassa havolasi kiritildi")
