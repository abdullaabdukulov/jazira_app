# -*- coding: utf-8 -*-
# Copyright (c) 2026, Jazira App
# License: MIT

import frappe

def run_manager_setup():
    """
    Ushbu funksiya 'bench migrate' paytida ishga tushadi.
    Optimallashtirilgan versiya: Agar sozlamalar to'g'ri bo'lsa, qayta yozmaydi.
    """
    print("=" * 60)
    print("JAZIRA APP: Manager va Ruxsatlarni tekshirish...")
    print("=" * 60)

    create_shift_types()
    create_roles()
    setup_users_and_permissions()
    
    frappe.db.commit()
    print("✅ JAZIRA SETUP: Tekshiruv yakunlandi!\n")

def create_shift_types():
    """Smenalarni yaratish (faqat yo'q bo'lsa)"""
    shifts = [
        {"name": "Smena 08:00-17:00", "start": "08:00:00", "end": "17:00:00"},
        {"name": "Smena 08:00-18:00", "start": "08:00:00", "end": "18:00:00"},
        {"name": "Smena 12:00-18:00", "start": "12:00:00", "end": "18:00:00"},
        {"name": "Smena 12:00-01:00", "start": "12:00:00", "end": "01:00:00"},
        {"name": "Smena 17:00-01:00", "start": "17:00:00", "end": "01:00:00"},
        {"name": "Smena 18:00-01:00", "start": "18:00:00", "end": "01:00:00"},
    ]

    if not frappe.db.exists("DocType", "Shift Type"):
        return

    for shift in shifts:
        if not frappe.db.exists("Shift Type", shift["name"]):
            try:
                doc = frappe.new_doc("Shift Type")
                doc.name = shift["name"]
                doc.shift_type_name = shift["name"]
                doc.start_time = shift["start"]
                doc.end_time = shift["end"]
                doc.flags.ignore_permissions = True
                doc.flags.ignore_mandatory = True
                doc.insert()
                print(f"  + Smena yaratildi: {shift['name']}")
            except Exception as e:
                print(f"  ⚠️ Smena xatosi: {e}")

def create_roles():
    """Rollar mavjudligini tekshirish"""
    roles = ["HR User", "Employee", "Attendance Manager", "Shift Manager", "Stock User"]
    
    for r in roles:
        if not frappe.db.exists("Role", r):
            try:
                new_role = frappe.new_doc("Role")
                new_role.role_name = r
                new_role.desk_access = 1 
                new_role.insert(ignore_permissions=True)
                print(f"  + Rol yaratildi: {r}")
            except Exception as e:
                print(f"  ⚠️ Rol xatosi ({r}): {e}")

def setup_users_and_permissions():
    """Managerlarni faqat kerak bo'lsa sozlash"""
    managers_data = [
        {"email": "admin_jazira@jazira.uz", "first_name": "Jazira Bosh Manager", "company": "Jazira", "is_parent_manager": True},
        {"email": "manager_xalq@jazira.uz", "first_name": "Xalq Banki Manager", "company": "Jazira Xalq Banki", "is_parent_manager": False},
        {"email": "manager_saripul@jazira.uz", "first_name": "Saripul Manager", "company": "Jazira Saripul", "is_parent_manager": False},
        {"email": "manager_smart@jazira.uz", "first_name": "Smart Manager", "company": "Jazira Smart", "is_parent_manager": False},
        {"email": "manager_sklad@jazira.uz", "first_name": "Sklad Manager", "company": "Jazira sklad", "is_parent_manager": False},
    ]

    roles_to_assign = ["HR User", "Employee", "Attendance Manager", "Shift Manager", "Stock User"]
    default_pass = "Jazira@2024!"

    for user_data in managers_data:
        email = user_data["email"]
        target_company = user_data["company"]
        is_parent = user_data["is_parent_manager"]

        # Kompaniya nomini aniqlashtirish
        real_company_name = frappe.db.get_value("Company", target_company, "name")
        if not real_company_name:
            continue

        # ---------------------------------------------------------
        # 1. USERNI TEKSHIRISH
        # ---------------------------------------------------------
        if frappe.db.exists("User", email):
            # User bor, uning parolini o'zgartirmaymiz!
            # Lekin rollarini tekshiramiz
            user_doc = frappe.get_doc("User", email)
            current_roles = [d.role for d in user_doc.roles]
            dirty_roles = False
            
            for r in roles_to_assign:
                if r not in current_roles:
                    user_doc.append("roles", {"role": r})
                    dirty_roles = True
            
            if dirty_roles:
                user_doc.save(ignore_permissions=True)
                print(f"  ↻ Rollar yangilandi: {email}")
        else:
            # User yo'q, yangi yaratamiz
            try:
                u = frappe.new_doc("User")
                u.email = email
                u.first_name = user_data["first_name"]
                u.enabled = 1
                u.send_welcome_email = 0
                u.new_password = default_pass
                u.flags.ignore_password_policy = True 
                
                # Rollarni shu yerning o'zida qo'shamiz
                for r in roles_to_assign:
                    u.append("roles", {"role": r})
                
                u.insert(ignore_permissions=True)
                print(f"  ✓ Yangi user yaratildi: {email}")
            except Exception as e:
                print(f"  ⚠️ User xatosi ({email}): {e}")
                continue

        # ---------------------------------------------------------
        # 2. RUXSATLARNI (PERMISSION) TEKSHIRISH
        # ---------------------------------------------------------
        
        # Parent manager uchun (Cheklov bo'lmasligi kerak)
        if is_parent:
            # Agar cheklov bo'lsa, olib tashlaymiz
            existing_perm = frappe.db.exists("User Permission", {"user": email, "allow": "Company"})
            if existing_perm:
                frappe.db.sql("DELETE FROM `tabUser Permission` WHERE user=%s AND allow='Company'", (email,))
                print(f"  🔓 {email}: Eski cheklovlar olib tashlandi (Parent).")
            else:
                # Jim turamiz, chunki hammasi joyida
                pass
        
        # Filial manager uchun (Cheklov bo'lishi kerak)
        else:
            # Aynan shu kompaniya uchun ruxsat bormi?
            is_correct_perm_exists = frappe.db.exists("User Permission", {
                "user": email,
                "allow": "Company",
                "for_value": real_company_name
            })

            if is_correct_perm_exists:
                # Ruxsat allaqachon to'g'ri, hech narsa qilmaymiz
                pass
            else:
                # Eski noto'g'ri ruxsatlarni tozalash
                frappe.db.sql("DELETE FROM `tabUser Permission` WHERE user=%s AND allow='Company'", (email,))
                
                # Yangisini qo'shish
                try:
                    perm = frappe.new_doc("User Permission")
                    perm.user = email
                    perm.allow = "Company"
                    perm.for_value = real_company_name
                    perm.is_default = 1
                    perm.insert(ignore_permissions=True, ignore_links=True)
                    print(f"  🔒 Ruxsat o'rnatildi: {email} -> {real_company_name}")
                except Exception as e:
                     print(f"  ⚠️ Ruxsat xatosi ({email}): {e}")