# -*- coding: utf-8 -*-
# Copyright (c) 2026, Jazira App
# License: MIT
"""
Manager Setup - Filial Boshqaruvi workspace + permissions
"""

import frappe
import json


def run_manager_setup():
    """Hook: jazira_app.jazira_app.setup.manager_setup.run_manager_setup"""
    print("\n" + "=" * 60)
    print("JAZIRA APP: Manager Setup")
    print("=" * 60)
    
    cleanup_old_workspaces()
    create_filial_workspace()
    setup_managers()
    hide_hr_workspaces()
    
    frappe.db.commit()
    print("\n✅ Setup completed!")
    print("=" * 60 + "\n")


def cleanup_old_workspaces():
    """O'chirish kerak bo'lgan workspacelar"""
    print("\n🗑️  Cleaning up old workspaces...")
    
    to_delete = [
        "Xodimlar",
        "Xodimlar Boshqaruvi",
    ]
    
    for ws_name in to_delete:
        if frappe.db.exists("Workspace", ws_name):
            try:
                frappe.delete_doc("Workspace", ws_name, force=True, ignore_permissions=True)
                print(f"  ✓ Deleted: {ws_name}")
            except:
                frappe.db.sql("DELETE FROM `tabWorkspace` WHERE name = %s", ws_name)
                print(f"  ✓ Force deleted: {ws_name}")
    
    frappe.db.commit()


def create_filial_workspace():
    """Filial Boshqaruvi - 4 ta shortcut"""
    ws_name = "Filial Boshqaruvi"
    
    print(f"\n🖥️  Creating workspace: {ws_name}")
    
    # Delete if exists
    if frappe.db.exists("Workspace", ws_name):
        frappe.delete_doc("Workspace", ws_name, force=True, ignore_permissions=True)
        frappe.db.commit()
    
    # Content layout
    content = [
        {"type": "spacer", "data": {"col": 12}},
        {"type": "shortcut", "data": {"shortcut_name": "Xodimlar", "col": 3}},
        {"type": "shortcut", "data": {"shortcut_name": "Kunlik Hisobot", "col": 3}},
        {"type": "shortcut", "data": {"shortcut_name": "Checkin", "col": 3}},
        {"type": "shortcut", "data": {"shortcut_name": "Checkin Report", "col": 3}},
    ]
    
    ws = frappe.new_doc("Workspace")
    ws.name = ws_name
    ws.label = ws_name
    ws.title = "Filial Boshqaruvi"
    ws.icon = "users"
    ws.module = "Jazira App"
    ws.public = 1
    ws.sequence_id = 1
    ws.content = json.dumps(content)
    
    # Shortcuts
    ws.append("shortcuts", {
        "label": "Xodimlar",
        "type": "DocType",
        "link_to": "Employee",
        "color": "Blue"
    })
    
    ws.append("shortcuts", {
        "label": "Kunlik Hisobot",
        "type": "Report",
        "link_to": "Employee Daily Hours",
        "color": "Green",
        "is_query_report": 1
    })
    
    ws.append("shortcuts", {
        "label": "Checkin",
        "type": "DocType",
        "link_to": "Employee Checkin",
        "color": "Orange"
    })
    
    ws.append("shortcuts", {
        "label": "Checkin Report",
        "type": "DocType",
        "link_to": "Employee Checkin",
        "color": "Yellow"
    })
    
    # Sidebar
    ws.append("links", {"label": "Asosiy", "type": "Card Break"})
    ws.append("links", {"label": "Xodimlar", "type": "Link", "link_type": "DocType", "link_to": "Employee"})
    ws.append("links", {"label": "Kunlik Hisobot", "type": "Link", "link_type": "Report", "link_to": "Employee Daily Hours"})
    ws.append("links", {"label": "Checkin", "type": "Link", "link_type": "DocType", "link_to": "Employee Checkin"})
    
    ws.flags.ignore_permissions = True
    ws.flags.ignore_links = True
    ws.insert()
    
    print(f"  ✓ Created: {ws_name}")


def setup_managers():
    """Manager users + HR Manager role + Company permission"""
    print("\n👤 Setting up managers...")
    
    managers = [
        ("admin_jazira@jazira.uz", "Bosh Manager", "Jazira", True),
        ("manager_xalq@jazira.uz", "Xalq Bank Manager", "Jazira Xalq Banki", False),
        ("manager_saripul@jazira.uz", "Saripul Manager", "Jazira Saripul", False),
        ("manager_smart@jazira.uz", "Smart Manager", "Jazira Smart", False),
        ("manager_sklad@jazira.uz", "Sklad Manager", "Jazira Sklad", False),
    ]
    
    password = "Jazira@2024!"
    
    # Kerakli rollar - HR Manager permission beradi
    required_roles = ["HR Manager", "HR User"]
    
    # Bloklash kerak modullar
    all_modules = frappe.get_all("Module Def", pluck="name")
    allowed_modules = ["Jazira App", "HR", "Setup"]
    
    for email, name, company, is_admin in managers:
        
        # 1. User yaratish
        if not frappe.db.exists("User", email):
            user = frappe.new_doc("User")
            user.email = email
            user.first_name = name
            user.enabled = 1
            user.send_welcome_email = 0
            user.new_password = password
            user.flags.ignore_password_policy = True
            user.insert(ignore_permissions=True)
            print(f"  ✓ Created: {email}")
        else:
            print(f"  - Exists: {email}")
        
        # 2. Rollarni o'rnatish
        user = frappe.get_doc("User", email)
        existing_roles = [r.role for r in user.roles]
        
        for role in required_roles:
            if role not in existing_roles:
                user.append("roles", {"role": role})
        
        # 3. Modullarni bloklash (admin uchun emas)
        if not is_admin:
            user.set("block_modules", [])
            for module in all_modules:
                if module not in allowed_modules:
                    user.append("block_modules", {"module": module})
        
        user.flags.ignore_permissions = True
        user.save()
        
        # 4. Company permission
        frappe.db.sql(
            "DELETE FROM `tabUser Permission` WHERE user = %s AND allow = 'Company'",
            email
        )
        
        if not is_admin:
            perm = frappe.new_doc("User Permission")
            perm.user = email
            perm.allow = "Company"
            perm.for_value = company
            perm.is_default = 1
            perm.apply_to_all_doctypes = 1
            perm.flags.ignore_permissions = True
            perm.insert()
            print(f"  🔒 {email} → {company}")
        else:
            print(f"  🔓 {email} → full access")


def hide_hr_workspaces():
    """Ortiqcha workspacelarni yashirish"""
    print("\n🙈 Hiding unnecessary workspaces...")
    
    hr_workspaces = [
        # HR modules
        "HR",
        "Recruitment",
        "Employee Lifecycle", 
        "Performance",
        "Shift & Attendance",
        "Expense Claims",
        "Leaves",
        "Payroll",
        # System
        "Home",
        "ERPNext Settings",
        "Settings",
        "Build",
        "Customization",
        "Integrations",
        "Tools",
        "Users",
    ]
    
    for ws_name in hr_workspaces:
        if frappe.db.exists("Workspace", ws_name):
            try:
                ws = frappe.get_doc("Workspace", ws_name)
                ws.public = 0
                ws.flags.ignore_permissions = True
                ws.save()
                print(f"  ✓ Hidden: {ws_name}")
            except Exception as e:
                print(f"  ⚠ {ws_name}: {e}")