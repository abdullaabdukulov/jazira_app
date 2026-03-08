"""
Payme, Click, Paynet to'lov usullarini qo'shadi (SQL orqali, ORM avoid).
"""
import frappe

CARD_MOPS = [
    {"name": "Payme",  "num": "1201"},
    {"name": "Click",  "num": "1202"},
    {"name": "Paynet", "num": "1203"},
]

ALL_COMPANIES = [
    {"name": "Jazira",           "abbr": "J"},
    {"name": "Jazira Smart",     "abbr": "JSmart"},
    {"name": "Jazira Saripul",   "abbr": "JSaripul"},
    {"name": "Jazira Xalq Banki","abbr": "JXBank"},
    {"name": "Jazira sklad",     "abbr": "Js"},
]

POS_PROFILES = ["URY POS - Smart", "URY POS - Saripul", "URY POS - Xalq bank"]


def _ensure_mop(mop_name):
    if frappe.db.exists("Mode of Payment", mop_name):
        return
    frappe.db.sql("""
        INSERT IGNORE INTO `tabMode of Payment`
            (name, creation, modified, modified_by, owner, docstatus, mode_of_payment, type, enabled)
        VALUES (%(n)s, NOW(), NOW(), 'Administrator', 'Administrator', 0, %(n)s, 'Bank', 1)
    """, {"n": mop_name})


def _add_to_pos_profile(pos_name, mop_name):
    exists = frappe.db.sql(
        "SELECT 1 FROM `tabPOS Payment Method` WHERE parent=%s AND mode_of_payment=%s",
        (pos_name, mop_name)
    )
    if not exists:
        idx = (frappe.db.sql("SELECT IFNULL(MAX(idx),0)+1 FROM `tabPOS Payment Method` WHERE parent=%s", pos_name)[0][0])
        row_name = f"{pos_name}-{mop_name}"
        frappe.db.sql("""
            INSERT IGNORE INTO `tabPOS Payment Method`
                (name, creation, modified, modified_by, owner, docstatus,
                 parent, parentfield, parenttype, mode_of_payment, `default`, idx)
            VALUES (%(n)s, NOW(), NOW(), 'Administrator', 'Administrator', 0,
                    %(pos)s, 'payments', 'POS Profile', %(mop)s, 0, %(idx)s)
        """, {"n": row_name, "pos": pos_name, "mop": mop_name, "idx": idx})


def _add_to_pos_opening(pos_name, mop_name):
    openings = frappe.db.sql(
        "SELECT name FROM `tabPOS Opening Entry` WHERE pos_profile=%s AND status='Open' AND docstatus=1",
        pos_name, as_list=True
    )
    for (opening_name,) in openings:
        exists = frappe.db.sql(
            "SELECT 1 FROM `tabPOS Opening Entry Detail` WHERE parent=%s AND mode_of_payment=%s",
            (opening_name, mop_name)
        )
        if not exists:
            idx = (frappe.db.sql("SELECT IFNULL(MAX(idx),0)+1 FROM `tabPOS Opening Entry Detail` WHERE parent=%s", opening_name)[0][0])
            row_name = f"{opening_name}-{mop_name}"
            frappe.db.sql("""
                INSERT IGNORE INTO `tabPOS Opening Entry Detail`
                    (name, creation, modified, modified_by, owner, docstatus,
                     parent, parentfield, parenttype, mode_of_payment, opening_amount, idx)
                VALUES (%(n)s, NOW(), NOW(), 'Administrator', 'Administrator', 0,
                        %(o)s, 'balance_details', 'POS Opening Entry', %(mop)s, 0, %(idx)s)
            """, {"n": row_name, "o": opening_name, "mop": mop_name, "idx": idx})


def execute():
    for mop in CARD_MOPS:
        _ensure_mop(mop["name"])
    for pos in POS_PROFILES:
        for mop in CARD_MOPS:
            _add_to_pos_profile(pos, mop["name"])
            _add_to_pos_opening(pos, mop["name"])
    frappe.db.commit()
    print("Payme, Click, Paynet qo'shildi.")
