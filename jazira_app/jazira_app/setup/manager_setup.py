# -*- coding: utf-8 -*-
# Copyright (c) 2026, Jazira App
# License: MIT
"""
Manager Setup - Filial boshqaruvi

Har bir manager faqat:
1. "Xodimlar Boshqaruvi" workspace ko'radi
2. O'z filiali xodimlarini ko'radi
3. Qolgan barcha workspace yashirin

Bosh Manager - barcha kompaniyalar, lekin faqat "Xodimlar Boshqaruvi"
Administrator - hamma narsani ko'radi (aralashmaslik)
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

# Manager rolining nomi
MANAGER_ROLE = "Filial Manager"

# Faqat shu workspace ko'rinadi managerlar uchun
ALLOWED_WORKSPACE = "Xodimlar Boshqaruvi"

# Managerlar foydalana oladigan modullar
ALLOWED_MODULES = ["Jazira App", "HR", "Setup"]


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
        
        # 2. Manager rolini yaratish
        setup_manager_role()
        
        # 3. Yangi workspace yaratish
        create_manager_workspace()
        
        # 4. Boshqa workspacelarni managerlardan yashirish
        restrict_other_workspaces()
        
        # 5. Managerlarni yaratish
        setup_managers()
        
        frappe.db.commit()
        
        print("\n" + "=" * 70)
        print("  ✅ SETUP MUVAFFAQIYATLI YAKUNLANDI!")
        print("=" * 70 + "\n")
        
    except Exception as e:
        print(f"\n❌ Xatolik: {e}")
        frappe.log_error(title="Manager Setup Error", message=str(e))
        raise


# ═══════════════════════════════════════════════════════════════════════════════
# CLEANUP
# ═══════════════════════════════════════════════════════════════════════════════

def cleanup_old_workspaces():
    """Eski workspacelarni o'chirish"""
    print("\n🗑️  Eski workspacelarni tozalash...")
    
    old_names = [
        "Xodimlar",
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


# ═══════════════════════════════════════════════════════════════════════════════
# ROLE
# ═══════════════════════════════════════════════════════════════════════════════

def setup_manager_role():
    """Filial Manager rolini yaratish"""
    print(f"\n🔐 Rol sozlanmoqda: {MANAGER_ROLE}")
    
    if not frappe.db.exists("Role", MANAGER_ROLE):
        role = frappe.new_doc("Role")
        role.role_name = MANAGER_ROLE
        role.desk_access = 1
        role.is_custom = 1
        role.flags.ignore_permissions = True
        role.insert()
        print(f"   ✓ Rol yaratildi: {MANAGER_ROLE}")
    else:
        print(f"   - Rol mavjud: {MANAGER_ROLE}")
    
    # DocType permissionlarini sozlash
    setup_doctype_permissions()


def setup_doctype_permissions():
    """DocType permissionlarini sozlash"""
    
    permissions = [
        # (DocType, read, write, create, delete)
        ("Employee", 1, 1, 0, 0),
        ("Employee Checkin", 1, 0, 0, 0),
        ("Attendance", 1, 0, 0, 0),
        ("Shift Type", 1, 0, 0, 0),
        ("Shift Assignment", 1, 1, 1, 0),
    ]
    
    for doctype, read, write, create, delete in permissions:
        if not frappe.db.exists("DocType", doctype):
            continue
            
        # Mavjud permissionni o'chirish
        frappe.db.sql("""
            DELETE FROM `tabDocPerm` 
            WHERE parent = %s AND role = %s
        """, (doctype, MANAGER_ROLE))
        
        # Yangi permission
        doc = frappe.get_doc("DocType", doctype)
        doc.append("permissions", {
            "role": MANAGER_ROLE,
            "read": read,
            "write": write,
            "create": create,
            "delete": delete,
            "report": 1,
            "export": 1,
        })
        doc.flags.ignore_permissions = True
        doc.save()
    
    print(f"   ✓ DocType permissionlar sozlandi")


# ═══════════════════════════════════════════════════════════════════════════════
# WORKSPACE
# ═══════════════════════════════════════════════════════════════════════════════

def create_manager_workspace():
    """Manager workspace yaratish - faqat Filial Manager ko'radi"""
    print(f"\n🖥️  Workspace yaratilmoqda: {ALLOWED_WORKSPACE}")
    
    # Mavjud bo'lsa o'chirish
    if frappe.db.exists("Workspace", ALLOWED_WORKSPACE):
        frappe.delete_doc("Workspace", ALLOWED_WORKSPACE, force=True, ignore_permissions=True)
        frappe.db.commit()
    
    # Workspace content
    content = [
        {
            "type": "header",
            "data": {"text": "<b>👋 Xush kelibsiz!</b>", "col": 12}
        },
        {
            "type": "paragraph", 
            "data": {"text": "Quyidagi bo'limlardan foydalaning:", "col": 12}
        },
        {"type": "spacer", "data": {"col": 12}},
        {"type": "shortcut", "data": {"shortcut_name": "Xodimlar Ro'yxati", "col": 4}},
        {"type": "shortcut", "data": {"shortcut_name": "Kunlik Hisobot", "col": 4}},
        {"type": "shortcut", "data": {"shortcut_name": "Davriy Hisobot", "col": 4}},
    ]
    
    ws = frappe.new_doc("Workspace")
    ws.name = ALLOWED_WORKSPACE
    ws.label = ALLOWED_WORKSPACE
    ws.title = "Xodimlar Boshqaruvi"
    ws.icon = "users"
    ws.module = "Jazira App"
    ws.public = 0  # Public EMAS - faqat ruxsat berilgan rollar ko'radi
    ws.sequence_id = 1
    ws.content = json.dumps(content)
    
    # ═══════════════════════════════════════════════════════════════
    # ROLES - faqat shu rollar ko'radi
    # ═══════════════════════════════════════════════════════════════
    ws.append("roles", {"role": MANAGER_ROLE})
    ws.append("roles", {"role": "System Manager"})  # Admin ham ko'rsin
    
    # ═══════════════════════════════════════════════════════════════
    # SHORTCUTS
    # ═══════════════════════════════════════════════════════════════
    ws.append("shortcuts", {
        "label": "Xodimlar Ro'yxati",
        "type": "DocType",
        "link_to": "Employee",
        "color": "#2196F3",
    })
    
    ws.append("shortcuts", {
        "label": "Kunlik Hisobot",
        "type": "Report",
        "link_to": "Employee Daily Hours",
        "color": "#4CAF50",
        "is_query_report": 1
    })
    
    ws.append("shortcuts", {
        "label": "Davriy Hisobot",
        "type": "Report", 
        "link_to": "Employee Period Hours",
        "color": "#FF9800",
        "is_query_report": 1
    })
    
    # ═══════════════════════════════════════════════════════════════
    # SIDEBAR LINKS
    # ═══════════════════════════════════════════════════════════════
    ws.append("links", {"label": "📊 Hisobotlar", "type": "Card Break"})
    ws.append("links", {
        "label": "Kunlik ish vaqti",
        "type": "Link",
        "link_type": "Report",
        "link_to": "Employee Daily Hours",
    })
    ws.append("links", {
        "label": "Davriy hisobot",
        "type": "Link",
        "link_type": "Report", 
        "link_to": "Employee Period Hours",
    })
    
    ws.append("links", {"label": "👥 Xodimlar", "type": "Card Break"})
    ws.append("links", {
        "label": "Xodimlar ro'yxati",
        "type": "Link",
        "link_type": "DocType",
        "link_to": "Employee",
    })
    ws.append("links", {
        "label": "Checkin jurnali",
        "type": "Link",
        "link_type": "DocType",
        "link_to": "Employee Checkin",
    })
    
    ws.flags.ignore_permissions = True
    ws.flags.ignore_links = True
    ws.insert()
    
    print(f"   ✅ Yaratildi: {ALLOWED_WORKSPACE}")
    print(f"   ✅ Faqat '{MANAGER_ROLE}' va 'System Manager' ko'radi")


def restrict_other_workspaces():
    """
    Boshqa workspacelarni Filial Manager dan yashirish.
    
    Usul: Har bir workspacega "System Manager" rolini qo'shish,
    shunda faqat System Manager ko'radi.
    
    Filial Manager bu workspacelarni ko'rmaydi.
    """
    print("\n🔒 Boshqa workspacelarni cheklash...")
    
    # "Xodimlar Boshqaruvi" dan boshqa barcha workspacelar
    all_workspaces = frappe.get_all("Workspace", pluck="name")
    
    count = 0
    for ws_name in all_workspaces:
        if ws_name == ALLOWED_WORKSPACE:
            continue
        
        try:
            ws = frappe.get_doc("Workspace", ws_name)
            
            # Public workspaceni private qilish va faqat System Manager ga berish
            if ws.public == 1:
                ws.public = 0
                
                # Mavjud rollarni tozalash
                ws.set("roles", [])
                
                # Faqat System Manager va Administrator
                ws.append("roles", {"role": "System Manager"})
                ws.append("roles", {"role": "Administrator"})
                
                ws.flags.ignore_permissions = True
                ws.save()
                count += 1
                
        except Exception as e:
            # Ba'zi standard workspacelar xato berishi mumkin
            pass
    
    print(f"   ✅ {count} ta workspace faqat Admin uchun cheklandi")
    print(f"   ℹ️  Filial Manager faqat '{ALLOWED_WORKSPACE}' ni ko'radi")


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
        # 2. Rollar - System Manager yo'q!
        # ═══════════════════════════════════════════════════════════════
        user.set("roles", [])
        
        # MUHIM: Bosh Manager ham System Manager emas!
        # Shunda u ham faqat "Xodimlar Boshqaruvi" ko'radi
        roles = [MANAGER_ROLE, "HR User", "HR Manager"]
        
        for role in roles:
            user.append("roles", {"role": role})
        
        print(f"      ✓ Rollar: {', '.join(roles)}")
        
        # ═══════════════════════════════════════════════════════════════
        # 3. Modullarni bloklash
        # ═══════════════════════════════════════════════════════════════
        user.set("block_modules", [])
        
        for module in all_modules:
            if module not in ALLOWED_MODULES:
                user.append("block_modules", {"module": module})
        
        print(f"      ✓ Faqat modullar: {', '.join(ALLOWED_MODULES)}")
        
        user.flags.ignore_permissions = True
        user.save()
        
        # ═══════════════════════════════════════════════════════════════
        # 4. Company permission
        # ═══════════════════════════════════════════════════════════════
        frappe.db.sql("""
            DELETE FROM `tabUser Permission` 
            WHERE user = %s AND allow = 'Company'
        """, email)
        
        if company:
            perm = frappe.new_doc("User Permission")
            perm.user = email
            perm.allow = "Company"
            perm.for_value = company
            perm.is_default = 1
            perm.apply_to_all_doctypes = 1
            perm.flags.ignore_permissions = True
            perm.insert()
            print(f"      🔒 Faqat kompaniya: {company}")
        else:
            print(f"      🔓 Barcha kompaniyalar")
    
    frappe.db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITY - Admin uchun workspacelarni qaytarish
# ═══════════════════════════════════════════════════════════════════════════════

def restore_all_workspaces():
    """
    Barcha workspacelarni public qilish (admin uchun).
    
    bench console da ishlatish:
    
    from jazira_app.jazira_app.setup.manager_setup import restore_all_workspaces
    restore_all_workspaces()
    """
    print("🔄 Barcha workspacelar qaytarilmoqda...")
    
    workspaces = frappe.get_all("Workspace", pluck="name")
    
    for ws_name in workspaces:
        try:
            ws = frappe.get_doc("Workspace", ws_name)
            ws.public = 1
            ws.set("roles", [])  # Barcha rollar uchun
            ws.flags.ignore_permissions = True
            ws.save()
            print(f"   ✓ Qaytarildi: {ws_name}")
        except Exception as e:
            print(f"   ⚠️ {ws_name}: {e}")
    
    frappe.db.commit()
    print(f"✅ {len(workspaces)} ta workspace qaytarildi")