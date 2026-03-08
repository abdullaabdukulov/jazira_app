# -*- coding: utf-8 -*-
# Copyright (c) 2026, Jazira App
# License: MIT

"""
Patch: Har bir filial uchun kassachi foydalanuvchi yaratish
===========================================================

Har bir filial uchun:
  1. Frappe User akaunti (URY Cashier roli bilan)
  2. POS Profile ga applicable_for_users qo'shish
  3. Branch user table ga (URY User) qo'shish
"""

import frappe


CASHIERS = [
    {
        "branch": "Smart",
        "email": "kassa.smart@jazira.uz",
        "full_name": "Kassachi - Smart",
        "pos_profile": "URY POS - Smart",
    },
    {
        "branch": "Saripul",
        "email": "kassa.saripul@jazira.uz",
        "full_name": "Kassachi - Saripul",
        "pos_profile": "URY POS - Saripul",
    },
    {
        "branch": "Xalq bank",
        "email": "kassa.xalqbank@jazira.uz",
        "full_name": "Kassachi - Xalq bank",
        "pos_profile": "URY POS - Xalq bank",
    },
]

NEW_PASSWORD = "Jazira@2026"
CASHIER_ROLES = ["URY Cashier", "Sales User", "Accounts User"]


def create_user(email, full_name):
    """Frappe User yaratish yoki mavjudini qaytarish."""
    if frappe.db.exists("User", email):
        print("  [OK]  User mavjud: " + email)
        return frappe.get_doc("User", email)

    user = frappe.get_doc({
        "doctype": "User",
        "email": email,
        "first_name": full_name,
        "enabled": 1,
        "send_welcome_email": 0,
        "new_password": NEW_PASSWORD,
        "roles": [{"role": r} for r in CASHIER_ROLES],
    })
    user.insert(ignore_permissions=True)
    print("  [NEW] User yaratildi: " + email)
    return user


def add_to_pos_profile(pos_profile_name, email):
    """POS Profile applicable_for_users ga qo'shish."""
    if not frappe.db.exists("POS Profile", pos_profile_name):
        print("  [!]  POS Profile topilmadi: " + pos_profile_name)
        return

    pos = frappe.get_doc("POS Profile", pos_profile_name)
    existing_users = [row.user for row in pos.applicable_for_users]

    if email not in existing_users:
        pos.append("applicable_for_users", {"user": email, "default": 1})
        pos.save(ignore_permissions=True)
        print("  [ADD] POS Profile " + pos_profile_name + " ga user qo'shildi: " + email)
    else:
        print("  [OK]  POS Profile " + pos_profile_name + ": user mavjud")


def add_to_branch(branch_name, email):
    """Branch user table ga URY User sifatida qo'shish."""
    if not frappe.db.exists("Branch", branch_name):
        print("  [!]  Branch topilmadi: " + branch_name)
        return

    branch = frappe.get_doc("Branch", branch_name)
    existing_users = [row.user for row in (branch.user or [])]

    if email not in existing_users:
        branch.append("user", {"user": email})
        branch.flags.ignore_mandatory = True
        branch.save(ignore_permissions=True)
        print("  [ADD] Branch " + branch_name + " ga user qo'shildi: " + email)
    else:
        print("  [OK]  Branch " + branch_name + ": user mavjud")


def execute():
    print("=" * 50)
    print("KASSACHI FOYDALANUVCHILARNI YARATISH")
    print("=" * 50)

    for cfg in CASHIERS:
        print("\n  [" + cfg["branch"] + "]")

        # 1. User akaunti
        create_user(cfg["email"], cfg["full_name"])

        # 2. POS Profile
        add_to_pos_profile(cfg["pos_profile"], cfg["email"])

        # 3. Branch user table
        add_to_branch(cfg["branch"], cfg["email"])

    frappe.db.commit()
    print("\n  [OK]  Barcha kassachilar sozlandi!")
    print("  Parol: " + NEW_PASSWORD)
