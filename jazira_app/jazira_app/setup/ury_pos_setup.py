# -*- coding: utf-8 -*-
# Copyright (c) 2026, Jazira App
# License: MIT

"""
URY POS — Filiallar sozlamasi
==============================

Uch filial: Smart, Saripul, Xalq bank

Ishlatish (bench console yoki execute):
    bench --site [site] execute jazira_app.jazira_app.setup.ury_pos_setup.execute

Patch sifatida (patches.txt orqali migrate da avtomatik):
    jazira_app.patches.v1_0.ury_pos_setup
"""

import frappe


# ============================================================
# KONFIGURATSIYA
# ============================================================

BRANCHES = [
    {
        "branch_name": "Smart",
        "company": "Jazira Smart",
        "abbr": "JSmart",
        "warehouse": "Sklad Smart - JSmart",
        "cost_center": "Main - JSmart",
        "tax_template": "Uzbekistan Tax - JSmart",
        "price_list": "Smart Menu",
        "mode_of_payment": "SMART CASH",
        "mop_account": "1110 - Cash - JSmart",
        "customer": "guest",
        "invoice_prefix": "SM",
        "buying_price_list": "Standard Buying",
        "ticket_count": 20,
    },
    {
        "branch_name": "Saripul",
        "company": "Jazira Saripul",
        "abbr": "JSaripul",
        "warehouse": "Sklad Saripul - JSaripul",
        "cost_center": "Main - JSaripul",
        "tax_template": "Uzbekistan Tax - JSaripul",
        "price_list": "Fillial uchun narxlar",
        "mode_of_payment": "Jazira",
        "mop_account": "1110 - Cash - JSaripul",
        "customer": "guest",
        "invoice_prefix": "SP",
        "buying_price_list": "Standard Buying",
        "ticket_count": 30,
    },
    {
        "branch_name": "Xalq bank",
        "company": "Jazira Xalq Banki",
        "abbr": "JXBank",
        "warehouse": "Sklad Xalq Bank - JXBank",
        "cost_center": "Main - JXBank",
        "tax_template": "Uzbekistan Tax - JXBank",
        "price_list": "Fillial uchun narxlar",
        "mode_of_payment": "Jazira",
        "mop_account": "1110 - Cash - JXBank",
        "customer": "guest",
        "invoice_prefix": "XB",
        "buying_price_list": "Standard Buying",
        "ticket_count": 30,
    },
]

PRODUCTION_UNITS = [
    {
        "branch": "Smart",
        "units": [
            {
                "name": "Smart - Oshpaz",
                "item_groups": ["Oshpaz"],
                "printer_name": "Smart - Kitchen Printer",
                "printer_ip": "192.168.1.100",
                "printer_port": 9100,
            }
        ],
    },
    {
        "branch": "Saripul",
        "units": [
            {
                "name": "Saripul - Oshpaz",
                "item_groups": ["Oshpaz"],
                "printer_name": "Saripul - Kitchen Printer",
                "printer_ip": "192.168.1.100",
                "printer_port": 9100,
            }
        ],
    },
    {
        "branch": "Xalq bank",
        "units": [
            {
                "name": "Xalq bank - Oshpaz",
                "item_groups": ["Oshpaz"],
                "printer_name": "Xalq bank - Kitchen Printer",
                "printer_ip": "192.168.1.100",
                "printer_port": 9100,
            },
            {
                "name": "Xalq bank - Koffe",
                "item_groups": ["Koffe"],
                "printer_name": "Xalq bank - Bar Printer",
                "printer_ip": "192.168.1.101",
                "printer_port": 9100,
            },
        ],
    },
]

MENU_ITEMS = [
    {"item_code": "Хот-дог",   "item_group": "Oshpaz", "rate": 15000},
    {"item_code": "Гамбургер", "item_group": "Oshpaz", "rate": 20000},
    {"item_code": "Кола 0.5",  "item_group": "Oshpaz", "rate": 8000},
    {"item_code": "Espresso",  "item_group": "Koffe",  "rate": 15000},
    {"item_code": "Americano", "item_group": "Koffe",  "rate": 18000},
    {"item_code": "Cappuccino","item_group": "Koffe",  "rate": 22000},
    {"item_code": "Latte",     "item_group": "Koffe",  "rate": 25000},
]


# ============================================================
# YORDAMCHI FUNKSIYALAR
# ============================================================

def log(msg):
    print(msg)


def find_account(company, root_type=None, account_type=None):
    filters = {"is_group": 0, "company": company}
    if root_type:
        filters["root_type"] = root_type
    if account_type:
        filters["account_type"] = account_type
    result = frappe.get_all("Account", filters=filters, fields=["name"], limit=1)
    return result[0].name if result else None


def setup_branch(branch_name):
    if frappe.db.exists("Branch", branch_name):
        log("  [OK]  Branch: " + branch_name)
        return
    doc = frappe.get_doc({"doctype": "Branch", "branch": branch_name})
    doc.insert(ignore_permissions=True, ignore_mandatory=True)
    log("  [NEW] Branch: " + branch_name)


def setup_mop_account(mop_name, company, account):
    """Mode of Payment'ga company account qo'shish."""
    if not frappe.db.exists("Mode of Payment", mop_name):
        log("  [!]  Mode of Payment topilmadi: " + mop_name)
        return
    mop = frappe.get_doc("Mode of Payment", mop_name)
    existing_cos = [r.company for r in mop.accounts]
    if company not in existing_cos:
        mop.append("accounts", {"company": company, "default_account": account})
        mop.save(ignore_permissions=True)
        log("  [ADD] MOP " + mop_name + ": " + company + " => " + account)
    else:
        log("  [OK]  MOP " + mop_name + ": " + company + " (mavjud)")


def setup_ury_room(branch_name):
    existing = frappe.get_all("URY Room", filters={"branch": branch_name}, limit=1)
    if existing:
        log("  [OK]  URY Room: " + existing[0].name)
        return existing[0].name
    label = branch_name + " - Main Hall"
    doc = frappe.get_doc({
        "doctype": "URY Room",
        "__newname": label,
        "branch": branch_name,
        "room_type": "AC",
    })
    doc.insert(ignore_permissions=True)
    log("  [NEW] URY Room: " + doc.name)
    return doc.name


def setup_ury_restaurant(branch_name, company, prefix, room_name, tax_tpl):
    # Tax template mavjudligini tekshirish
    if tax_tpl and not frappe.db.exists("Sales Taxes and Charges Template", tax_tpl):
        log(f"  [WARN] Tax template topilmadi: {tax_tpl} — bo'sh qoldirildi")
        tax_tpl = ""

    existing = frappe.get_all("URY Restaurant", filters={"branch": branch_name}, limit=1)
    if existing:
        doc = frappe.get_doc("URY Restaurant", existing[0].name)
        changed = False
        if doc.company != company:
            doc.company = company
            changed = True
        if not doc.default_room and room_name:
            doc.default_room = room_name
            changed = True
        if changed:
            doc.save(ignore_permissions=True)
            log("  [UPD] URY Restaurant: " + doc.name)
        else:
            log("  [OK]  URY Restaurant: " + doc.name)
        return doc

    doc = frappe.get_doc({
        "doctype": "URY Restaurant",
        "__newname": branch_name,
        "company": company,
        "branch": branch_name,
        "invoice_series_prefix": prefix,
        "default_room": room_name,
        "default_tax_template": tax_tpl or "",
    })
    doc.insert(ignore_permissions=True)
    log("  [NEW] URY Restaurant: " + doc.name)
    return doc


def _ensure_billing_role(pos_doc, role):
    """POS Profile role_allowed_for_billing ga rol qo'shish (agar yo'q bo'lsa)."""
    existing = [r.role for r in (pos_doc.role_allowed_for_billing or [])]
    if role not in existing:
        pos_doc.append("role_allowed_for_billing", {"role": role})


def setup_pos_profile(cfg, restaurant_name):
    pos_name = "URY POS - " + cfg["branch_name"]
    company = cfg["company"]
    write_off = find_account(company, account_type="Expense Account") or find_account(company, root_type="Expense")
    income = find_account(company, root_type="Income")

    # Tax template mavjudligini tekshirish
    tax_tpl = cfg["tax_template"]
    if tax_tpl and not frappe.db.exists("Sales Taxes and Charges Template", tax_tpl):
        log(f"  [WARN] Tax template topilmadi: {tax_tpl} — bo'sh qoldirildi")
        tax_tpl = ""
    cfg = {**cfg, "tax_template": tax_tpl}

    if frappe.db.exists("POS Profile", pos_name):
        doc = frappe.get_doc("POS Profile", pos_name)
        doc.company = company
        doc.warehouse = cfg["warehouse"]
        doc.currency = "UZS"
        doc.selling_price_list = cfg["price_list"]
        doc.cost_center = cfg["cost_center"]
        doc.restaurant = restaurant_name
        doc.branch = cfg["branch_name"]
        doc.customer = cfg["customer"]
        doc.disabled = 0
        if write_off:
            doc.write_off_account = write_off
        doc.write_off_cost_center = cfg["cost_center"]
        if income:
            doc.income_account = income
        if cfg["tax_template"]:
            doc.taxes_and_charges = cfg["tax_template"]
        if not doc.payments:
            doc.append("payments", {"mode_of_payment": cfg["mode_of_payment"], "default": 1})
        doc.custom_kot_naming_series = "KOT-.YYYY.-.####"
        doc.custom_enable_multiple_cashier = 1
        _ensure_billing_role(doc, "URY Cashier")
        doc.save(ignore_permissions=True)
        log("  [UPD] POS Profile: " + pos_name)
        return doc

    vals = {
        "doctype": "POS Profile",
        "__newname": pos_name,
        "company": company,
        "warehouse": cfg["warehouse"],
        "currency": "UZS",
        "selling_price_list": cfg["price_list"],
        "cost_center": cfg["cost_center"],
        "write_off_cost_center": cfg["cost_center"],
        "customer": cfg["customer"],
        "restaurant": restaurant_name,
        "branch": cfg["branch_name"],
        "disabled": 0,
        "custom_kot_naming_series": "KOT-.YYYY.-.####",
        "custom_enable_multiple_cashier": 1,
        "payments": [{"mode_of_payment": cfg["mode_of_payment"], "default": 1}],
        "role_allowed_for_billing": [{"role": "URY Cashier"}],
    }
    if write_off:
        vals["write_off_account"] = write_off
    if income:
        vals["income_account"] = income
    if cfg["tax_template"]:
        vals["taxes_and_charges"] = cfg["tax_template"]
    doc = frappe.get_doc(vals)
    doc.insert(ignore_permissions=True)
    log("  [NEW] POS Profile: " + pos_name)
    return doc


def setup_ury_menu(branch_name, rest_doc, menu_items):
    existing = frappe.get_all("URY Menu", filters={"branch": branch_name}, limit=1)
    if existing:
        menu_doc = frappe.get_doc("URY Menu", existing[0].name)
        log("  [OK]  URY Menu: " + menu_doc.name)
    else:
        label = branch_name + " Menu"
        menu_doc = frappe.get_doc({
            "doctype": "URY Menu",
            "__newname": label,
            "branch": branch_name,
            "enabled": 1,
        })
        menu_doc.insert(ignore_permissions=True, ignore_mandatory=True)
        log("  [NEW] URY Menu: " + menu_doc.name)

    # active_menu bog'lash
    rest_doc.reload()
    if not rest_doc.active_menu:
        rest_doc.active_menu = menu_doc.name
        rest_doc.save(ignore_permissions=True)
        log("  [UPD] Restaurant active_menu => " + menu_doc.name)

    # Item'larni qo'shish
    existing_items = [r.item for r in menu_doc.items]
    added = 0
    for item in menu_items:
        if item["item_code"] not in existing_items:
            menu_doc.append("items", {"item": item["item_code"], "rate": item["rate"]})
            added += 1
    if added > 0:
        menu_doc.save(ignore_permissions=True)
        log("  [UPD] URY Menu: " + str(added) + " ta item qo'shildi")

    return menu_doc.name


def setup_ury_report_settings(branch_name, buying_pl):
    if frappe.db.exists("URY Report Settings", branch_name):
        log("  [OK]  URY Report Settings: " + branch_name)
        return
    try:
        doc = frappe.get_doc({
            "doctype": "URY Report Settings",
            "branch": branch_name,
            "extended_hours": 0,
            "buying_price_list": buying_pl,
        })
        doc.insert(ignore_permissions=True)
        log("  [NEW] URY Report Settings: " + doc.name)
    except Exception as e:
        log("  [!]   URY Report Settings: " + str(e))


def setup_network_printer(printer_name, ip, port):
    if frappe.db.exists("Network Printer Settings", printer_name):
        log("    [OK]  Network Printer: " + printer_name)
        return printer_name
    doc = frappe.get_doc({
        "doctype": "Network Printer Settings",
        "__newname": printer_name,
        "server_ip": ip,
        "port": port,
        "printer_name": "placeholder",
    })
    doc.insert(ignore_permissions=True, ignore_mandatory=True)
    log("    [NEW] Network Printer: " + printer_name)
    return printer_name


def setup_production_unit(unit_name, pos_profile, item_groups, printer_name):
    if frappe.db.exists("URY Production Unit", unit_name):
        log("  [OK]  URY Production Unit: " + unit_name)
        return
    doc = frappe.get_doc({
        "doctype": "URY Production Unit",
        "production": unit_name,
        "pos_profile": pos_profile,
        "item_groups": [{"item_group": ig} for ig in item_groups],
        "printer_settings": [{"printer": printer_name, "bill": 1}],
    })
    doc.insert(ignore_permissions=True)
    log("  [NEW] URY Production Unit: " + unit_name)


def setup_tickets(branch_name, rest_name, room_name, count):
    existing_count = frappe.db.count("URY Table", filters={"branch": branch_name})
    if existing_count >= count:
        log("  [OK]  URY Table: " + str(existing_count) + " ta ticket mavjud")
        return
    created = 0
    for i in range(1, count + 1):
        ticket_name = branch_name + "-" + str(i)
        if frappe.db.exists("URY Table", ticket_name):
            continue
        doc = frappe.get_doc({
            "doctype": "URY Table",
            "__newname": ticket_name,
            "restaurant": rest_name,
            "restaurant_room": room_name,
            "branch": branch_name,
            "is_take_away": 0,
            "occupied": 0,
        })
        doc.insert(ignore_permissions=True)
        created += 1
    log("  [NEW] URY Table: " + str(created) + " ta ticket yaratildi (1-" + str(count) + ")")


# ============================================================
# ASOSIY FUNKSIYA
# ============================================================

def execute():
    """
    Barcha filiallar uchun URY POS sozlamasi.
    Idempotent: mavjud bo'lsa skip, bo'lmasa yaratadi.
    """
    log("=" * 60)
    log("URY POS BRANCH SETUP")
    log("=" * 60)

    for cfg in BRANCHES:
        br = cfg["branch_name"]
        log("\n" + "=" * 50)
        log("FILIAL: " + br + " (" + cfg["company"] + ")")
        log("=" * 50)

        # 1. Branch
        log("\n  --- Branch ---")
        setup_branch(br)

        # 2. Mode of Payment account
        log("\n  --- Mode of Payment ---")
        setup_mop_account(cfg["mode_of_payment"], cfg["company"], cfg["mop_account"])

        # 3. URY Room
        log("\n  --- URY Room ---")
        room_name = setup_ury_room(br)

        # 4. URY Restaurant
        log("\n  --- URY Restaurant ---")
        rest_doc = setup_ury_restaurant(
            br, cfg["company"], cfg["invoice_prefix"],
            room_name, cfg["tax_template"]
        )

        # 5. POS Profile
        log("\n  --- POS Profile ---")
        setup_pos_profile(cfg, rest_doc.name)

        # 6. URY Menu + items
        log("\n  --- URY Menu ---")
        setup_ury_menu(br, rest_doc, MENU_ITEMS)

        # 7. URY Report Settings
        log("\n  --- URY Report Settings ---")
        setup_ury_report_settings(br, cfg["buying_price_list"])

        # 8. Ticket raqamlar
        log("\n  --- URY Table (Tickets) ---")
        setup_tickets(br, rest_doc.name, room_name, cfg["ticket_count"])

    # Production Units (barcha filiallar bo'lgandan keyin)
    log("\n" + "=" * 50)
    log("PRODUCTION UNITS")
    log("=" * 50)
    for pu_cfg in PRODUCTION_UNITS:
        br = pu_cfg["branch"]
        pos_profile = "URY POS - " + br
        log("\n  [" + br + "]")
        for unit in pu_cfg["units"]:
            printer = setup_network_printer(
                unit["printer_name"], unit["printer_ip"], unit["printer_port"]
            )
            setup_production_unit(
                unit["name"], pos_profile, unit["item_groups"], printer
            )

    frappe.db.commit()
    log("\n" + "=" * 60)
    log("URY POS SETUP COMPLETED!")
    log("=" * 60)
