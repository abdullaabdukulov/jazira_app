# -*- coding: utf-8 -*-
# Copyright (c) 2026, Jazira App
# License: MIT

"""
Patch: Sklad toldirish va POS Opening
======================================

1. Purchase Receipt: Jazira Sklad → Sklad baza - Js  (tan narx)
2. Stock Reconciliation: har filial uchun ochilish qoldig'i (tan narx + 10%)
3. POS Opening Entry: har filial uchun (100,000 so'm ochilish qoldig'i)

Tan narxlar:
    Хот-дог   : 10 000 so'm  → filialga 11 000 so'm
    Гамбургер : 15 000 so'm  → filialga 16 500 so'm
    Кола 0.5  :  5 000 so'm  → filialga  5 500 so'm

Miqdorlar: Sklad Baza 100 ta, har filial 50 ta (Кола: 100 ta)
"""

import frappe
from frappe.utils import now_datetime, today


MARKUP = 1.10          # 10% ustama
OPENING_CASH = 100000  # POS ochilish qoldig'i (so'm)

STOCK_ITEMS = [
    {"item_code": "Хот-дог",   "qty_baza": 100, "qty_filial": 50,  "rate": 10000, "uom": "Nos"},
    {"item_code": "Гамбургер", "qty_baza": 100, "qty_filial": 50,  "rate": 15000, "uom": "Nos"},
    {"item_code": "Кола 0.5",  "qty_baza": 100, "qty_filial": 100, "rate": 5000,  "uom": "Nos"},
]

BRANCHES = [
    {
        "branch": "Smart",
        "company": "Jazira Smart",
        "warehouse": "Sklad Smart - JSmart",
        "pos_profile": "URY POS - Smart",
        "cashier": "kassa.smart@jazira.uz",
        "mode_of_payment": "SMART CASH",
        "temp_account": "1910 - Temporary Opening - JSmart",
    },
    {
        "branch": "Saripul",
        "company": "Jazira Saripul",
        "warehouse": "Sklad Saripul - JSaripul",
        "pos_profile": "URY POS - Saripul",
        "cashier": "kassa.saripul@jazira.uz",
        "mode_of_payment": "Jazira",
        "temp_account": "1910 - Temporary Opening - JSaripul",
    },
    {
        "branch": "Xalq bank",
        "company": "Jazira Xalq Banki",
        "warehouse": "Sklad Xalq Bank - JXBank",
        "pos_profile": "URY POS - Xalq bank",
        "cashier": "kassa.xalqbank@jazira.uz",
        "mode_of_payment": "Jazira",
        "temp_account": "1910 - Temporary Opening - JXBank",
    },
]


# ─── 1. STOCK ENTRY (Material Receipt) Sklad Baza ────────────────────────────

def create_baza_stock_entry():
    """Sklad baza - Js ga ochilish stoki (Material Receipt)."""
    # Avvalgi hujjat borligini tekshirish
    exists = frappe.db.exists("Stock Entry", {
        "company": "Jazira sklad",
        "stock_entry_type": "Material Receipt",
        "docstatus": 1,
        "remarks": "Jazira POS Setup - Opening Stock",
    })
    if exists:
        print("  [OK]  Stock Entry mavjud (Sklad Baza): " + exists)
        return

    items = []
    for item in STOCK_ITEMS:
        items.append({
            "item_code": item["item_code"],
            "qty": item["qty_baza"],
            "basic_rate": item["rate"],
            "uom": item["uom"],
            "t_warehouse": "Sklad baza - Js",
        })

    doc = frappe.get_doc({
        "doctype": "Stock Entry",
        "stock_entry_type": "Material Receipt",
        "company": "Jazira sklad",
        "posting_date": today(),
        "posting_time": "08:00:00",
        "remarks": "Jazira POS Setup - Opening Stock",
        "items": items,
    })
    doc.insert(ignore_permissions=True)
    doc.submit()
    frappe.db.commit()
    print("  [NEW] Stock Entry (Material Receipt): " + doc.name + " → Sklad baza - Js")


# ─── 2. STOCK RECONCILIATION (filial uchun) ──────────────────────────────────

def create_stock_reconciliation(cfg):
    """Filial uchun ochilish qoldig'ini o'rnatish (tan narx + 10% ustama)."""
    # Mavjud ochilish stoki bormi?
    exists = frappe.db.exists("Stock Reconciliation", {
        "company": cfg["company"],
        "warehouse": cfg["warehouse"],
        "docstatus": 1,
        "purpose": "Opening Stock",
        "remarks": "Jazira POS Setup - Opening Stock",
    })
    if exists:
        print("  [OK]  Stock Reconciliation mavjud: " + cfg["branch"])
        return

    items = []
    for item in STOCK_ITEMS:
        filial_rate = round(item["rate"] * MARKUP)
        items.append({
            "item_code": item["item_code"],
            "warehouse": cfg["warehouse"],
            "qty": item["qty_filial"],
            "valuation_rate": filial_rate,
        })

    doc = frappe.get_doc({
        "doctype": "Stock Reconciliation",
        "company": cfg["company"],
        "posting_date": today(),
        "posting_time": "08:00:00",
        "purpose": "Opening Stock",
        "expense_account": cfg["temp_account"],
        "remarks": "Jazira POS Setup - Opening Stock",
        "items": items,
    })
    doc.insert(ignore_permissions=True)
    doc.submit()
    frappe.db.commit()
    print("  [NEW] Stock Reconciliation: " + cfg["branch"] +
          " (" + str(len(items)) + " ta item, 10% ustama bilan)")


# ─── 3. POS OPENING ENTRY ─────────────────────────────────────────────────────

def create_pos_opening(cfg):
    """Filial kassachisi uchun POS ochilishi."""
    # Avvalgi ochiq POS session bormi?
    exists = frappe.db.exists("POS Opening Entry", {
        "pos_profile": cfg["pos_profile"],
        "status": "Open",
        "docstatus": 1,
    })
    if exists:
        print("  [OK]  POS Opening Entry mavjud (Open): " + cfg["branch"])
        return

    doc = frappe.get_doc({
        "doctype": "POS Opening Entry",
        "pos_profile": cfg["pos_profile"],
        "company": cfg["company"],
        "user": cfg["cashier"],
        "period_start_date": now_datetime(),
        "posting_date": today(),
        "balance_details": [
            {
                "mode_of_payment": cfg["mode_of_payment"],
                "opening_amount": OPENING_CASH,
            }
        ],
    })
    doc.insert(ignore_permissions=True)
    doc.submit()
    frappe.db.commit()
    print("  [NEW] POS Opening Entry: " + cfg["branch"] +
          " | " + cfg["cashier"] +
          " | " + str(OPENING_CASH) + " so'm")


# ─── ASOSIY ───────────────────────────────────────────────────────────────────

def execute():
    print("=" * 60)
    print("SKLAD TOLDIRISH VA POS OPENING")
    print("=" * 60)

    # 1. Sklad Baza ga Material Receipt
    print("\n1. STOCK ENTRY - MATERIAL RECEIPT (Sklad Baza)")
    print("-" * 40)
    try:
        create_baza_stock_entry()
    except Exception as e:
        print("  [!]  Sklad Baza Stock Entry xatosi: " + str(e))

    # 2. Har filial uchun Stock Reconciliation
    print("\n2. STOCK RECONCILIATION (Filiallar)")
    print("-" * 40)
    for cfg in BRANCHES:
        print("  [" + cfg["branch"] + "]")
        try:
            create_stock_reconciliation(cfg)
        except Exception as e:
            print("  [!]  " + cfg["branch"] + " xatosi: " + str(e))

    # 3. POS Opening Entry
    print("\n3. POS OPENING ENTRY")
    print("-" * 40)
    for cfg in BRANCHES:
        print("  [" + cfg["branch"] + "]")
        try:
            create_pos_opening(cfg)
        except Exception as e:
            print("  [!]  " + cfg["branch"] + " xatosi: " + str(e))

    frappe.db.commit()
    print("\n" + "=" * 60)
    print("TAYYOR!")
    print("  Sklad Baza: 100 ta x 3 item (tan narxda)")
    print("  Har filial: 50-100 ta x 3 item (tan narx + 10%)")
    print("  POS ochiq: 100,000 so'm bilan")
    print("=" * 60)
