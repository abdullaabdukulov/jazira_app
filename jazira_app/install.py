"""
Installation script for Dahua Integration custom fields.

Run manually if fixtures don't install automatically:
    bench --site your-site.local execute jazira_app.install.after_install
"""

import frappe


def after_install():
    """Called after app installation."""
    create_custom_fields()
    frappe.db.commit()
    print("Dahua Integration: Custom fields created successfully.")


def create_custom_fields():
    """Create custom fields on Employee and Employee Checkin."""
    custom_fields = [
        # Employee field for device ID mapping
        {
            "dt": "Employee",
            "fieldname": "attendance_device_id",
            "fieldtype": "Data",
            "insert_after": "employee_name",
            "label": "Attendance Device ID",
            "unique": 0,
            "in_list_view": 1,
            "in_standard_filter": 1,
            "description": "User ID configured in Dahua access control device (e.g., 777)"
        },
        # Employee Checkin fields
        {
            "dt": "Employee Checkin",
            "fieldname": "dahua_event_id",
            "fieldtype": "Data",
            "insert_after": "device_id",
            "label": "Dahua Event ID",
            "read_only": 1,
            "unique": 1,
            "description": "Unique identifier for Dahua event deduplication"
        },
        {
            "dt": "Employee Checkin",
            "fieldname": "dahua_attendance_state",
            "fieldtype": "Int",
            "insert_after": "dahua_event_id",
            "label": "Dahua Attendance State",
            "read_only": 1,
            "description": "Original AttendanceState from Dahua device (1=IN, 2=OUT, 3=RETURN, 5=TEMP_OUT)"
        },
        {
            "dt": "Employee Checkin",
            "fieldname": "checkin_source",
            "fieldtype": "Select",
            "insert_after": "dahua_attendance_state",
            "label": "Checkin Source",
            "options": "\nManual\nDahua\nImport",
            "read_only": 1,
            "in_standard_filter": 1,
            "description": "Source of the checkin record"
        },
        {
            "dt": "Employee Checkin",
            "fieldname": "checkin_reason",
            "fieldtype": "Select",
            "insert_after": "checkin_source",
            "label": "Checkin Reason",
            "options": "\nIN\nOUT\nTEMP_OUT\nRETURN",
            "read_only": 1,
            "in_list_view": 1,
            "in_standard_filter": 1,
            "description": "Semantic meaning: IN/OUT for shift start/end, TEMP_OUT/RETURN for breaks"
        }
    ]
    
    for field_def in custom_fields:
        # Check if field already exists
        existing = frappe.db.exists("Custom Field", {
            "dt": field_def["dt"],
            "fieldname": field_def["fieldname"]
        })
        
        if existing:
            print(f"Custom field {field_def['fieldname']} already exists, skipping.")
            continue
        
        # Create custom field
        doc = frappe.get_doc({
            "doctype": "Custom Field",
            **field_def
        })
        doc.insert(ignore_permissions=True)
        print(f"Created custom field: {field_def['fieldname']}")


def before_uninstall():
    """Called before app uninstallation."""
    # Optionally remove custom fields
    # Uncomment if you want fields removed on uninstall
    # remove_custom_fields()
    pass


def remove_custom_fields():
    """Remove custom fields from Employee Checkin."""
    fields_to_remove = [
        "dahua_event_id",
        "dahua_attendance_state", 
        "checkin_source",
        "checkin_reason"
    ]
    
    for fieldname in fields_to_remove:
        cf = frappe.db.get_value("Custom Field", {
            "dt": "Employee Checkin",
            "fieldname": fieldname
        })
        if cf:
            frappe.delete_doc("Custom Field", cf, force=True)
            print(f"Removed custom field: {fieldname}")
    
    frappe.db.commit()
