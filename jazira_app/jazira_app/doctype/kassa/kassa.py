# -*- coding: utf-8 -*-
# Copyright (c) 2026, Jazira App
# License: MIT

"""
Kassa v3.6 - Company Mode of Payment'dan avtomatik

Company tekshiruvi FAQAT Расходы uchun!
Перемещение da har xil company bo'lishi mumkin.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class Kassa(Document):
    """Kassa Document."""
    
    def validate(self):
        self.validate_summa()
        self.set_company_and_accounts()
        self.validate_transfer()
        self.validate_expense_kontragent()
        self.clear_irrelevant_fields()
    
    def validate_summa(self):
        """Summa > 0 bo'lishi kerak."""
        if self.summa <= 0:
            frappe.throw(_("Summa 0 dan katta bo'lishi kerak"))
    
    def set_company_and_accounts(self):
        """Mode of Payment'dan company va account olish."""
        if self.oborot == "Перемещение":
            source_company = None
            target_company = None
            
            if self.transfer_source_display:
                info = get_mode_of_payment_info(self.transfer_source_display)
                if info.get("account"):
                    self.payment_account = info["account"]
                    self.company = info["company"]
                    source_company = info["company"]
                else:
                    frappe.throw(_("'{0}' uchun hisob topilmadi.").format(self.transfer_source_display))
            
            if self.target_account:
                info2 = get_mode_of_payment_info(self.target_account)
                if info2.get("account"):
                    self.payment_account_2 = info2["account"]
                    target_company = info2["company"]
                else:
                    frappe.throw(_("'{0}' uchun hisob topilmadi.").format(self.target_account))
            
            # MUHIM: Перемещение da company bir xil bo'lishi SHART
            if source_company and target_company and source_company != target_company:
                frappe.throw(
                    _("Перемещение: Manba ({0}) va maqsad ({1}) hisob bir xil kompaniyaga tegishli bo'lishi kerak.").format(
                        source_company, target_company
                    )
                )
        else:
            if self.source_account:
                info = get_mode_of_payment_info(self.source_account)
                if info.get("account"):
                    self.payment_account = info["account"]
                    self.company = info["company"]
                else:
                    frappe.throw(_("'{0}' uchun hisob topilmadi.").format(self.source_account))
        
        # Приход + Supplier/Employee/Shareholder uchun ogohlantirish
        if self.oborot == "Приход" and self.party_type in ["Supplier", "Employee", "Shareholder"]:
            self._warn_prihod_payable_party()
    
    def validate_transfer(self):
        """Перемещение uchun validatsiya."""
        if self.oborot == "Перемещение":
            if not self.transfer_source_display:
                frappe.throw(_("'Qaysi hisobdan' majburiy"))
            if not self.target_account:
                frappe.throw(_("'Qaysi hisobga' majburiy"))
            if self.transfer_source_display == self.target_account:
                frappe.throw(_("Manba va maqsad hisob bir xil bo'lishi mumkin emas"))
    
    def validate_expense_kontragent(self):
        """
        FAQAT Расходы uchun company tekshiruvi!
        Expense account Mode of Payment bilan bir xil company bo'lishi kerak.
        """
        if self.party_type == "Расходы" and self.expense_kontragent:
            account_data = frappe.db.get_value(
                "Account", 
                self.expense_kontragent, 
                ["root_type", "company"], 
                as_dict=True
            )
            
            if not account_data:
                frappe.throw(_("Xarajat kontragenti topilmadi."))
            
            if account_data.root_type != "Expense":
                frappe.throw(_("Xarajat kontragenti faqat Expense account bo'lishi kerak."))
            
            if self.company and account_data.company != self.company:
                frappe.throw(
                    _("Xarajat kontragenti '{0}' kompaniyasiga tegishli bo'lishi kerak.").format(self.company)
                )
    
    def _warn_prihod_payable_party(self):
        """
        Приход + Supplier/Employee/Shareholder uchun ogohlantirish.
        
        Bu holat odatda "avans qaytishi" uchun ishlatiladi:
        - Avval Supplier/Employee/Shareholder ga avans berilgan (Расход)
        - Endi ular pulni qaytaryapti (Приход)
        
        JE mantiq: Cash Debit, Payable Credit (qarz kamayadi)
        """
        if not self.kontragent or not self.company:
            return
        
        try:
            from erpnext.accounts.party import get_party_account
            party_account = get_party_account(self.party_type, self.kontragent, self.company)
            
            if party_account:
                # Party account balansini tekshirish
                balance = frappe.db.sql("""
                    SELECT SUM(debit) - SUM(credit) as balance
                    FROM `tabGL Entry`
                    WHERE account = %s 
                        AND party_type = %s 
                        AND party = %s 
                        AND is_cancelled = 0
                """, (party_account, self.party_type, self.kontragent), as_dict=True)
                
                current_balance = balance[0].balance if balance and balance[0].balance else 0
                
                # Agar balans 0 yoki credit (manfiy) bo'lsa - ogohlantirish
                if current_balance <= 0:
                    frappe.msgprint(
                        _("⚠️ Diqqat: '{0}' ({1}) uchun avans balansi topilmadi yoki 0.<br><br>"
                          "Bu operatsiya odatda <b>avans qaytishi</b> uchun ishlatiladi - "
                          "ya'ni avval siz ularga pul bergansiz (Расход), endi ular qaytaryapti.<br><br>"
                          "Joriy balans: {2}<br><br>"
                          "Agar bu oddiy daromad bo'lsa, 'Прочее лицо' yoki 'Customer' tanlang.").format(
                            self.kontragent, self.party_type, current_balance
                        ),
                        title=_("Avans qaytishi haqida"),
                        indicator="orange"
                    )
        except Exception:
            # Xato bo'lsa ham davom etsin
            pass
    
    def clear_irrelevant_fields(self):
        """Oborot ga qarab keraksiz field'larni tozalash."""
        if self.oborot == "Перемещение":
            self.party_type = None
            self.kontragent = None
            self.expense_kontragent = None
            self.prochee_kontragent = None
            self.filial = None
            self.source_account = None
            self.source_balance = 0
        else:
            self.transfer_source_display = None
            self.transfer_source_balance = 0
            self.target_account = None
            self.target_balance = 0
            self.payment_account_2 = None
            
            if self.party_type != "Расходы":
                self.filial = None
    
    # =========================================================================
    # JOURNAL ENTRY
    # =========================================================================
    
    def on_submit(self):
        """Submit bo'lganda Journal Entry yaratish."""
        self.create_journal_entry()
    
    def on_cancel(self):
        """Cancel bo'lganda Journal Entry bekor qilish."""
        self.cancel_journal_entry()
    
    def create_journal_entry(self):
        """Journal Entry yaratish."""
        if not self.company:
            frappe.throw(_("Company topilmadi"))
        
        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.posting_date = self.date
        je.company = self.company
        je.user_remark = f"Kassa: {self.name} - {self.oborot}"
        
        if self.oborot == "Перемещение":
            self._add_transfer_entries(je)
        elif self.oborot == "Приход":
            self._add_income_entries(je)
        elif self.oborot == "Расход":
            self._add_expense_entries(je)
        
        je.insert(ignore_permissions=True)
        je.submit()
        
        frappe.db.set_value("Kassa", self.name, "journal_entry", je.name)
        
        frappe.msgprint(
            _("Journal Entry yaratildi: {0}").format(
                f'<a href="/app/journal-entry/{je.name}">{je.name}</a>'
            ),
            indicator="green"
        )
    
    def _add_transfer_entries(self, je):
        """Перемещение - hisobdan hisobga o'tkazma."""
        # Target - Debit
        je.append("accounts", {
            "account": self.payment_account_2,
            "debit_in_account_currency": self.summa,
            "credit_in_account_currency": 0
        })
        # Source - Credit
        je.append("accounts", {
            "account": self.payment_account,
            "debit_in_account_currency": 0,
            "credit_in_account_currency": self.summa
        })
    
    def _add_income_entries(self, je):
        """Приход - pul kelishi."""
        # Cash - Debit
        je.append("accounts", {
            "account": self.payment_account,
            "debit_in_account_currency": self.summa,
            "credit_in_account_currency": 0
        })
        
        # Kontragent - Credit
        if self.party_type in ["Customer", "Supplier", "Employee", "Shareholder"]:
            party_account = self._get_party_account()
            je.append("accounts", {
                "account": party_account,
                "party_type": self.party_type,
                "party": self.kontragent,
                "debit_in_account_currency": 0,
                "credit_in_account_currency": self.summa
            })
        elif self.party_type == "Расходы":
            je.append("accounts", {
                "account": self.expense_kontragent,
                "debit_in_account_currency": 0,
                "credit_in_account_currency": self.summa
            })
        elif self.party_type == "Прочее лицо":
            income_account = self._get_default_income_account()
            je.append("accounts", {
                "account": income_account,
                "debit_in_account_currency": 0,
                "credit_in_account_currency": self.summa
            })
    
    def _add_expense_entries(self, je):
        """Расход - pul chiqishi."""
        # Kontragent - Debit
        if self.party_type == "Расходы":
            je.append("accounts", {
                "account": self.expense_kontragent,
                "debit_in_account_currency": self.summa,
                "credit_in_account_currency": 0
            })
        elif self.party_type in ["Customer", "Supplier", "Employee", "Shareholder"]:
            party_account = self._get_party_account()
            je.append("accounts", {
                "account": party_account,
                "party_type": self.party_type,
                "party": self.kontragent,
                "debit_in_account_currency": self.summa,
                "credit_in_account_currency": 0
            })
        elif self.party_type == "Прочее лицо":
            expense_account = self._get_default_expense_account()
            je.append("accounts", {
                "account": expense_account,
                "debit_in_account_currency": self.summa,
                "credit_in_account_currency": 0
            })
        
        # Cash - Credit
        je.append("accounts", {
            "account": self.payment_account,
            "debit_in_account_currency": 0,
            "credit_in_account_currency": self.summa
        })
    
    def _get_party_account(self):
        """Party uchun account olish."""
        from erpnext.accounts.party import get_party_account
        return get_party_account(self.party_type, self.kontragent, self.company)
    
    def _get_default_income_account(self):
        """Default income account."""
        account = frappe.db.get_value("Company", self.company, "default_income_account")
        if not account:
            account = frappe.db.get_value(
                "Account",
                {"company": self.company, "root_type": "Income", "is_group": 0},
                "name"
            )
        return account
    
    def _get_default_expense_account(self):
        """Default expense account."""
        account = frappe.db.get_value("Company", self.company, "default_expense_account")
        if not account:
            account = frappe.db.get_value(
                "Account",
                {"company": self.company, "root_type": "Expense", "is_group": 0},
                "name"
            )
        return account
    
    def cancel_journal_entry(self):
        """Journal Entry bekor qilish."""
        if self.journal_entry:
            je = frappe.get_doc("Journal Entry", self.journal_entry)
            if je.docstatus == 1:
                je.cancel()
                frappe.msgprint(
                    _("Journal Entry bekor qilindi: {0}").format(self.journal_entry),
                    indicator="orange"
                )


# =============================================================================
# WHITELISTED METHODS
# =============================================================================

@frappe.whitelist()
def get_mode_of_payment_info(mode_of_payment: str) -> dict:
    """
    Mode of Payment'dan birinchi account, company va balans olish.
    """
    if not mode_of_payment:
        return {"account": "", "company": "", "balance": 0}
    
    # Birinchi account ni olish
    mopa = frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": mode_of_payment, "default_account": ["is", "set"]},
        ["default_account", "company"],
        as_dict=True
    )
    
    if not mopa:
        return {"account": "", "company": "", "balance": 0}
    
    balance = get_account_balance(mopa.default_account)
    
    return {
        "account": mopa.default_account,
        "company": mopa.company,
        "balance": balance
    }


@frappe.whitelist()
def get_account_balance(account: str) -> float:
    """Account balansini olish."""
    if not account:
        return 0
    
    balance = frappe.db.sql("""
        SELECT SUM(debit) - SUM(credit) as balance
        FROM `tabGL Entry`
        WHERE account = %s AND is_cancelled = 0
    """, account, as_dict=True)
    
    return balance[0].balance if balance and balance[0].balance else 0


@frappe.whitelist()
def get_mode_of_payments_by_company(company: str, exclude_mop: str = None) -> list:
    """
    Berilgan company uchun Mode of Payment ro'yxatini qaytarish.
    
    Args:
        company: Kompaniya nomi
        exclude_mop: Ro'yxatdan chiqarib tashlash kerak bo'lgan Mode of Payment
    
    Returns:
        Mode of Payment nomlari ro'yxati
    """
    if not company:
        return []
    
    # Mode of Payment Account child table orqali company bo'yicha filter
    mop_list = frappe.db.sql("""
        SELECT DISTINCT mopa.parent as name
        FROM `tabMode of Payment Account` mopa
        INNER JOIN `tabMode of Payment` mop ON mop.name = mopa.parent
        WHERE mopa.company = %(company)s
            AND mopa.default_account IS NOT NULL
            AND mop.enabled = 1
    """, {"company": company}, as_dict=True)
    
    result = [m.name for m in mop_list]
    
    # Exclude qilish kerak bo'lsa
    if exclude_mop and exclude_mop in result:
        result.remove(exclude_mop)
    
    return result


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_filtered_mode_of_payments(doctype, txt, searchfield, start, page_len, filters):
    """
    Link field uchun Mode of Payment query.
    target_account field da ishlatiladi.
    
    Filters:
        - company: faqat shu company'ga tegishli MoP lar
        - exclude: bu MoP ni ro'yxatdan chiqarish
    """
    company = filters.get("company", "")
    exclude = filters.get("exclude", "")
    
    if not company:
        # Company yo'q bo'lsa, barcha enabled MoP larni ko'rsat
        return frappe.db.sql("""
            SELECT name
            FROM `tabMode of Payment`
            WHERE enabled = 1
                AND name LIKE %(txt)s
                AND name != %(exclude)s
            ORDER BY name
            LIMIT %(start)s, %(page_len)s
        """, {
            "txt": f"%{txt}%",
            "exclude": exclude or "",
            "start": start,
            "page_len": page_len
        })
    
    # Company bo'yicha filter
    return frappe.db.sql("""
        SELECT DISTINCT mopa.parent as name
        FROM `tabMode of Payment Account` mopa
        INNER JOIN `tabMode of Payment` mop ON mop.name = mopa.parent
        WHERE mopa.company = %(company)s
            AND mopa.default_account IS NOT NULL
            AND mop.enabled = 1
            AND mopa.parent LIKE %(txt)s
            AND mopa.parent != %(exclude)s
        ORDER BY mopa.parent
        LIMIT %(start)s, %(page_len)s
    """, {
        "company": company,
        "txt": f"%{txt}%",
        "exclude": exclude or "",
        "start": start,
        "page_len": page_len
    })
