"""
Dahua Device DocType Controller

Maps physical Dahua access control devices to ERPNext companies.
Each device can only be assigned to one company at a time.
"""

import frappe
from frappe.model.document import Document


class DahuaDevice(Document):
    def validate(self):
        """Validate device configuration."""
        self.validate_company()
    
    def validate_company(self):
        """Ensure company is a valid leaf company (not a group)."""
        if self.company:
            is_group = frappe.db.get_value("Company", self.company, "is_group")
            if is_group:
                frappe.throw(
                    f"Company '{self.company}' is a group company. "
                    "Please select a specific sub-company."
                )
    
    def before_save(self):
        """Clean up device_sn before saving."""
        if self.device_sn:
            self.device_sn = self.device_sn.strip()
