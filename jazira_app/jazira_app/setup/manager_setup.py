# -*- coding: utf-8 -*-
# Copyright (c) 2026, Jazira App
# License: MIT
"""
Manager Setup - Filial boshqaruvi

Har bir manager faqat:
1. O'z filiali xodimlarini ko'radi
2. 3 ta sahifaga dostup: Xodimlar, Kunlik Hisobot, Davriy Hisobot
3. Qolgan barcha narsa yashirin

Bosh Manager - hammaga dostup
"""

import frappe
import json


# ═══════════════════════════════════════════════════════════════════════════════
# KONFIGURATSIYA
# ═══════════════════════════════════════════════════════════════════════════════

MANAGERS = [
    {
        "email": "admin@jazira.uz",
        "name": "Bosh Manager",
        "company": None,  # None = barcha kompaniyalar
        "is_admin": True,
        "password": "Jazira@2024!"
    },
    {
        "email": "manager_xalqbank@jazira.uz",
        "name": "Xalq Bank Manager",
        "company": "Jazira Xalq Banki",
        "is_admin": False,
        "password": "Jazira@2024!"
    },
    {
        "email": "manager_saripul@jazira.uz",
        "name": "Saripul Manager", 
        "company": "Jazira Saripul",
        "is_admin": False,
        "password": "Jazira@2024!"
    },
    {
        "email": "manager_smart@jazira.uz",
        "name": "Smart Manager",
        "company": "Jazira Smart",
        "is_admin": False,
        "password": "Jazira@2024!"
    },
    {
        "email": "manager_sklad@jazira.uz",
        "name": "Sklad Manager",
        "company": "Jazira Sklad",
        "is_admin": False,
        "password": "Jazira@2024!"
    },
]

# Managerlar foydalana oladigan modullar
ALLOWED_MODULES = ["Jazira App", "HR", "Setup"]

# Yashiriladigan workspacelar
WORKSPACES_TO_HIDE = [
    # HR modules
    "HR",
    "Recruitment",
    "Employee Lifecycle",
    "Performance",
    "Shift & Attendance",
    "Expense Claims",
    "Leaves",
    "Payroll",
    # Accounting
    "Accounting",
    "Receivables",
    "Payables",
    # Stock
    "Stock",
    "Buying",
    "Selling",
    # Manufacturing
    "Manufacturing",
    # System
    "Home",
    "ERPNext Settings",
    "Settings",
    "Build",
    "Customization",
    "Integrations",
    "Tools",
    "Users",
    "Website",
    "CRM",
    "Support",
    "Projects",
    "Assets",
    "Quality",
]


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def run_manager_setup():
    """
    Hook: jazira_app.jazira_app.setup.manager_setup.run_manager_setup
    
    after_migrate da chaqiriladi
    """
    print("\n" + "=" * 70)
    print("  🏢 JAZIRA APP: MANAGER SETUP")
    print("=" * 70)
    
    try:
        # 1. Eski workspacelarni o'chirish
        cleanup_old_workspaces()
        
        # 2. Yangi workspace yaratish
        create_filial_workspace()
        
        # 3. Manager rolini yaratish/sozlash
        setup_manager_role()
        
        # 4. Managerlarni yaratish
        setup_managers()
        
        # 5. Ortiqcha workspacelarni yashirish
        hide_unnecessary_workspaces()
        
        frappe.db.commit()
        
        print("\n" + "=" * 70)
        print("  ✅ SETUP MUVAFFAQIYATLI YAKUNLANDI!")
        print("=" * 70 + "\n")
        
    except Exception as e:
        print(f"\n❌ Xatolik: {e}")
        frappe.log_error(title="Manager Setup Error", message=str(e))
        raise


# ═══════════════════════════════════════════════════════════════════════════════
# WORKSPACE
# ═══════════════════════════════════════════════════════════════════════════════

def cleanup_old_workspaces():
    """Eski workspacelarni o'chirish"""
    print("\n🗑️  Eski workspacelarni tozalash...")
    
    old_names = [
        "Xodimlar",
        "Xodimlar Boshqaruvi", 
        "Filial Boshqaruvi",
        "Manager Panel",
    ]
    
    for ws_name in old_names:
        if frappe.db.exists("Workspace", ws_name):
            try:
                frappe.delete_doc("Workspace", ws_name, force=True, ignore_permissions=True)
                print(f"   ✓ O'chirildi: {ws_name}")
            except Exception:
                frappe.db.sql("DELETE FROM `tabWorkspace` WHERE name = %s", ws_name)
                print(f"   ✓ Majburiy o'chirildi: {ws_name}")
    
    frappe.db.commit()


def create_filial_workspace():
    """Yangi biznes-do'stona workspace yaratish"""
    ws_name = "Xodimlar Boshqaruvi"
    
    print(f"\n🖥️  Workspace yaratilmoqda: {ws_name}")
    
    # Mavjud bo'lsa o'chirish
    if frappe.db.exists("Workspace", ws_name):
        frappe.delete_doc("Workspace", ws_name, force=True, ignore_permissions=True)
        frappe.db.commit()
    
    # Workspace content (ko'rinish)
    content = [
        {
            "type": "header",
            "data": {
                "text": "<b>👋 Xush kelibsiz!</b>",
                "col": 12
            }
        },
        {
            "type": "paragraph", 
            "data": {
                "text": "Quyidagi bo'limlardan foydalaning:",
                "col": 12
            }
        },
        {"type": "spacer", "data": {"col": 12}},
        {"type": "shortcut", "data": {"shortcut_name": "Xodimlar Ro'yxati", "col": 4}},
        {"type": "shortcut", "data": {"shortcut_name": "Kunlik Hisobot", "col": 4}},
        {"type": "shortcut", "data": {"shortcut_name": "Davriy Hisobot", "col": 4}},
    ]
    
    ws = frappe.new_doc("Workspace")
    ws.name = ws_name
    ws.label = ws_name
    ws.title = "Xodimlar Boshqaruvi"
    ws.icon = "users"
    ws.module = "Jazira App"
    ws.public = 1
    ws.sequence_id = 1
    ws.content = json.dumps(content)
    
    # ═══════════════════════════════════════════════════════════════
    # SHORTCUTS (kartochkalar)
    # ═══════════════════════════════════════════════════════════════
    
    ws.append("shortcuts", {
        "label": "Xodimlar Ro'yxati",
        "type": "DocType",
        "link_to": "Employee",
        "icon": "users",
        "color": "#2196F3",  # Ko'k
        "format": "{}"
    })
    
    ws.append("shortcuts", {
        "label": "Kunlik Hisobot",
        "type": "Report",
        "link_to": "Employee Daily Hours",
        "icon": "calendar",
        "color": "#4CAF50",  # Yashil
        "is_query_report": 1
    })
    
    ws.append("shortcuts", {
        "label": "Davriy Hisobot",
        "type": "Report", 
        "link_to": "Employee Period Hours",
        "icon": "trending-up",
        "color": "#FF9800",  # Sariq
        "is_query_report": 1
    })
    
    # ═══════════════════════════════════════════════════════════════
    # SIDEBAR (chap menyu)
    # ═══════════════════════════════════════════════════════════════
    
    # Asosiy bo'lim
    ws.append("links", {
        "label": "📊 Hisobotlar",
        "type": "Card Break"
    })
    
    ws.append("links", {
        "label": "Kunlik ish vaqti",
        "type": "Link",
        "link_type": "Report",
        "link_to": "Employee Daily Hours",
        "icon": "calendar"
    })
    
    ws.append("links", {
        "label": "Davriy hisobot",
        "type": "Link",
        "link_type": "Report", 
        "link_to": "Employee Period Hours",
        "icon": "bar-chart-2"
    })
    
    # Xodimlar bo'limi
    ws.append("links", {
        "label": "👥 Xodimlar",
        "type": "Card Break"
    })
    
    ws.append("links", {
        "label": "Xodimlar ro'yxati",
        "type": "Link",
        "link_type": "DocType",
        "link_to": "Employee",
        "icon": "users"
    })
    
    ws.append("links", {
        "label": "Checkin jurnali",
        "type": "Link",
        "link_type": "DocType",
        "link_to": "Employee Checkin",
        "icon": "log-in"
    })
    
    ws.flags.ignore_permissions = True
    ws.flags.ignore_links = True
    ws.insert()
    
    print(f"   ✅ Yaratildi: {ws_name}")


# ═══════════════════════════════════════════════════════════════════════════════
# ROLE VA PERMISSION
# ═══════════════════════════════════════════════════════════════════════════════

def setup_manager_role():
    """Filial Manager rolini yaratish/sozlash"""
    role_name = "Filial Manager"
    
    print(f"\n🔐 Rol sozlanmoqda: {role_name}")
    
    # Rol yaratish
    if not frappe.db.exists("Role", role_name):
        role = frappe.new_doc("Role")
        role.role_name = role_name
        role.desk_access = 1
        role.is_custom = 1
        role.flags.ignore_permissions = True
        role.insert()
        print(f"   ✓ Rol yaratildi: {role_name}")
    else:
        print(f"   - Rol mavjud: {role_name}")
    
    # Permission sozlash
    setup_doctype_permissions(role_name)


def setup_doctype_permissions(role_name):
    """DocType permissionlarni sozlash"""
    
    # Ruxsat beriladigan DocTypelar va ularning permissionlari
    permissions = [
        # DocType, Read, Write, Create, Delete
        ("Employee", 1, 1, 0, 0),           # O'qish va tahrirlash
        ("Employee Checkin", 1, 0, 0, 0),   # Faqat o'qish
        ("Attendance", 1, 0, 0, 0),         # Faqat o'qish
        ("Shift Type", 1, 0, 0, 0),         # Faqat o'qish
        ("Shift Assignment", 1, 1, 1, 0),   # Shift tayinlash
    ]
    
    for doctype, read, write, create, delete in permissions:
        # Mavjud permissionni o'chirish
        frappe.db.sql("""
            DELETE FROM `tabDocPerm` 
            WHERE parent = %s AND role = %s
        """, (doctype, role_name))
        
        # Yangi permission qo'shish
        doc = frappe.get_doc("DocType", doctype)
        doc.append("permissions", {
            "role": role_name,
            "read": read,
            "write": write,
            "create": create,
            "delete": delete,
            "report": 1,
            "export": 1,
            "if_owner": 0
        })
        doc.flags.ignore_permissions = True
        doc.save()
    
    print(f"   ✓ Permissionlar sozlandi")


# ═══════════════════════════════════════════════════════════════════════════════
# MANAGER USERS
# ═══════════════════════════════════════════════════════════════════════════════

def setup_managers():
    """Manager userlarni yaratish va sozlash"""
    print("\n👤 Managerlar sozlanmoqda...")
    
    all_modules = frappe.get_all("Module Def", pluck="name")
    
    for mgr in MANAGERS:
        email = mgr["email"]
        name = mgr["name"]
        company = mgr["company"]
        is_admin = mgr["is_admin"]
        password = mgr["password"]
        
        print(f"\n   📧 {email}")
        
        # ═══════════════════════════════════════════════════════════════
        # 1. User yaratish
        # ═══════════════════════════════════════════════════════════════
        if not frappe.db.exists("User", email):
            user = frappe.new_doc("User")
            user.email = email
            user.first_name = name
            user.enabled = 1
            user.send_welcome_email = 0
            user.new_password = password
            user.flags.ignore_password_policy = True
            user.flags.ignore_permissions = True
            user.insert()
            print(f"      ✓ User yaratildi")
        else:
            print(f"      - User mavjud")
        
        user = frappe.get_doc("User", email)
        
        # ═══════════════════════════════════════════════════════════════
        # 2. Rollar
        # ═══════════════════════════════════════════════════════════════
        user.set("roles", [])
        
        if is_admin:
            # Bosh manager - to'liq dostup
            roles = ["System Manager", "HR Manager", "HR User", "Filial Manager"]
        else:
            # Filial manager - cheklangan
            roles = ["Filial Manager", "HR User"]
        
        for role in roles:
            user.append("roles", {"role": role})
        
        print(f"      ✓ Rollar: {', '.join(roles)}")
        
        # ═══════════════════════════════════════════════════════════════
        # 3. Modullarni bloklash (admin uchun emas)
        # ═══════════════════════════════════════════════════════════════
        user.set("block_modules", [])
        
        if not is_admin:
            for module in all_modules:
                if module not in ALLOWED_MODULES:
                    user.append("block_modules", {"module": module})
            print(f"      ✓ Faqat ruxsat: {', '.join(ALLOWED_MODULES)}")
        else:
            print(f"      ✓ Barcha modullarga dostup")
        
        user.flags.ignore_permissions = True
        user.save()
        
        # ═══════════════════════════════════════════════════════════════
        # 4. Company permission (filial cheklovi)
        # ═══════════════════════════════════════════════════════════════
        
        # Eski permissionlarni o'chirish
        frappe.db.sql("""
            DELETE FROM `tabUser Permission` 
            WHERE user = %s AND allow = 'Company'
        """, email)
        
        if company and not is_admin:
            # Faqat o'z kompaniyasini ko'radi
            perm = frappe.new_doc("User Permission")
            perm.user = email
            perm.allow = "Company"
            perm.for_value = company
            perm.is_default = 1
            perm.apply_to_all_doctypes = 1
            perm.flags.ignore_permissions = True
            perm.insert()
            print(f"      🔒 Faqat: {company}")
        else:
            print(f"      🔓 Barcha kompaniyalar")
    
    frappe.db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# WORKSPACE HIDING
# ═══════════════════════════════════════════════════════════════════════════════

def hide_unnecessary_workspaces():
    """
    Workspacelarni yashirish EMAS, faqat "Xodimlar Boshqaruvi" ga 
    Filial Manager rolini qo'shish.
    
    Administrator (System Manager) hamma narsani ko'radi.
    Filial Manager faqat "Xodimlar Boshqaruvi" ni ko'radi.
    """
    print("\n🔐 Workspace permissionlarni sozlash...")
    
    ws_name = "Xodimlar Boshqaruvi"
    
    if frappe.db.exists("Workspace", ws_name):
        # Filial Manager uchun workspace permission
        # Bu workspace public=1 bo'lgani uchun hammaga ko'rinadi
        # Lekin Filial Manager faqat ruxsat berilgan DocType/Reportlarni ochadi
        print(f"   ✓ '{ws_name}' barcha managerlar uchun tayyor")
    
    print(f"   ℹ️  Administrator (System Manager) barcha workspacelarni ko'radi")
    print(f"   ℹ️  Filial Manager faqat ruxsat berilgan sahifalarni ochadi")


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def reset_manager_password(email, new_password):
    """Manager parolini o'zgartirish"""
    if frappe.db.exists("User", email):
        user = frappe.get_doc("User", email)
        user.new_password = new_password
        user.flags.ignore_password_policy = True
        user.flags.ignore_permissions = True
        user.save()
        frappe.db.commit()
        return True
    return False


def add_manager(email, name, company, password="Jazira@2024!"):
    """Yangi manager qo'shish"""
    MANAGERS.append({
        "email": email,
        "name": name,
        "company": company,
        "is_admin": False,
        "password": password
    })
    setup_managers()


def restore_all_workspaces():
    """
    Barcha yashirilgan workspacelarni qaytarish
    Administrator uchun - bench console'da ishlatish:
    
    from jazira_app.jazira_app.setup.manager_setup import restore_all_workspaces
    restore_all_workspaces()
    """
    print("🔄 Barcha workspacelar qaytarilmoqda...")
    
    workspaces = frappe.get_all("Workspace", filters={"public": 0}, pluck="name")
    
    for ws_name in workspaces:
        try:
            ws = frappe.get_doc("Workspace", ws_name)
            ws.public = 1
            ws.flags.ignore_permissions = True
            ws.save()
            print(f"   ✓ Qaytarildi: {ws_name}")
        except Exception as e:
            print(f"   ⚠️ {ws_name}: {e}")
    
    frappe.db.commit()
    print(f"✅ {len(workspaces)} ta workspace qaytarildi")