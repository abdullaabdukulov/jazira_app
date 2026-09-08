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


def ensure_kassa_link_fields():
    """Payment Entry va Journal Entry'ga "Kassa" Link maydonini qo'shadi
    va eski hujjatlarni to'ldiradi.

    Kassa hujjat yaratganda PE'ning reference_no'siga / JE'ning
    user_remark'iga kassa nomini yozardi — lekin bu oddiy matn, bosib
    o'tib bo'lmasdi. Link maydoni bilan hujjat formasidan to'g'ridan-to'g'ri
    Kassa'ga o'tiladi, Kassa'ning "Connections" bo'limida esa yaratilgan
    hujjatlari ko'rinadi.
    """
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    field = {
        "fieldname": "custom_kassa",
        "label": "Kassa",
        "fieldtype": "Link",
        "options": "Kassa",
        "read_only": 1,
        # Kassa amend/duplicate bo'lganda eski havola ko'chib qolmasin
        "no_copy": 1,
        "print_hide": 1,
        "in_standard_filter": 1,
        "description": "Ushbu hujjatni yaratgan Kassa hujjati",
    }
    for dt, insert_after in (("Payment Entry", "reference_no"),
                             ("Journal Entry", "cheque_no")):
        existed = frappe.db.exists(
            "Custom Field", {"dt": dt, "fieldname": "custom_kassa"})
        create_custom_fields({dt: [dict(field, insert_after=insert_after)]})
        if not existed:
            print(f"✅ {dt}.custom_kassa maydoni yaratildi")

    _backfill_kassa_links()


def _backfill_kassa_links():
    """Eski hujjatlarga Kassa havolasini kiritadi (idempotent).

    Asosiy manba — Kassa hujjatining o'z link maydonlari: reference_no /
    user_remark'dan ko'ra ishonchli. Kassa amend qilinganda eski (bekor
    qilingan) hujjat kassadan uzilib qoladi — ular uchun zaxira sifatida
    JE'ning "Kassa: KASSA-..." remark'idagi nom o'qiladi.
    """
    for dt, join in (
        ("Payment Entry",
         "pe.name IN (k.payment_entry, k.payment_entry_receive, k.payment_entry_supplier)"),
        ("Journal Entry", "pe.name = k.journal_entry"),
    ):
        pairs = frappe.db.sql(
            f"""
            SELECT k.name AS kassa, pe.name AS doc
            FROM `tabKassa` k
            JOIN `tab{dt}` pe ON {join}
            WHERE IFNULL(pe.custom_kassa, '') = ''
            """,
            as_dict=True,
        )
        for row in pairs:
            frappe.db.set_value(dt, row.doc, "custom_kassa", row.kassa,
                                update_modified=False)
        if pairs:
            print(f"✅ {len(pairs)} ta eski {dt}'ga Kassa havolasi kiritildi")

    # Zaxira: remark'i "Kassa: ..." bilan boshlanadigan, lekin hech qaysi
    # kassa link qilmagan JE'lar (masalan, kassa amend qilingandagi eskilari)
    orphans = frappe.db.sql(
        """
        SELECT name, user_remark FROM `tabJournal Entry`
        WHERE IFNULL(custom_kassa, '') = ''
          AND user_remark LIKE 'Kassa: KASSA-%'
        """,
        as_dict=True,
    )
    fixed = 0
    for row in orphans:
        kassa_name = row.user_remark[len("Kassa: "):].split(" - ")[0].strip()
        if kassa_name and frappe.db.exists("Kassa", kassa_name):
            frappe.db.set_value("Journal Entry", row.name, "custom_kassa",
                                kassa_name, update_modified=False)
            fixed += 1
    if fixed:
        print(f"✅ {fixed} ta JE'ga remark orqali Kassa havolasi tiklandi")
