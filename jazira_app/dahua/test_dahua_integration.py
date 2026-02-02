"""
Test Suite for Dahua Access Control Integration

Run with: bench run-tests --app jazira_app

These tests cover:
- Event filtering (Code, AttendanceState, DataSource)
- Device mapping validation
- Employee resolution
- Deduplication
- Time conversion
- Full integration scenarios
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from datetime import datetime
from unittest.mock import patch, MagicMock
import json


class TestDahuaIntegration(FrappeTestCase):
    """Test cases for Dahua webhook integration."""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._create_test_data()
    
    @classmethod
    def _create_test_data(cls):
        """Create test companies, devices, and employees."""
        # Create test company if not exists
        if not frappe.db.exists("Company", "Test Jazira Sub"):
            company = frappe.get_doc({
                "doctype": "Company",
                "company_name": "Test Jazira Sub",
                "default_currency": "UZS",
                "country": "Uzbekistan"
            })
            company.insert(ignore_permissions=True)
        
        # Create test device
        if not frappe.db.exists("Dahua Device", "TEST123"):
            device = frappe.get_doc({
                "doctype": "Dahua Device",
                "device_sn": "TEST123",
                "company": "Test Jazira Sub",
                "is_active": 1,
                "device_name": "Test Device"
            })
            device.insert(ignore_permissions=True)
        
        # Create test employee
        if not frappe.db.exists("Employee", "TEST-EMP-001"):
            emp = frappe.get_doc({
                "doctype": "Employee",
                "employee_name": "Test Employee",
                "employee_id": "777",
                "company": "Test Jazira Sub",
                "gender": "Male",
                "date_of_birth": "1990-01-01",
                "date_of_joining": "2020-01-01"
            })
            emp.insert(ignore_permissions=True)
        
        frappe.db.commit()
    
    def tearDown(self):
        """Clean up test checkins after each test."""
        frappe.db.delete("Employee Checkin", {"checkin_source": "Dahua"})
        frappe.db.commit()
        # Clear Redis cache
        frappe.cache().delete_keys("dahua:event:*")
    
    # =========================================================================
    # Filter Tests
    # =========================================================================
    
    def test_tc01_door_status_ignored(self):
        """TC-01: DoorStatus events should be ignored."""
        from jazira_app.dahua.api import _process_event
        
        event = {
            "Code": "DoorStatus",
            "Data": {"Status": "Open"}
        }
        result = _process_event(event, "TEST123")
        self.assertFalse(result)
    
    def test_tc02_invalid_state_ignored(self):
        """TC-02: AttendanceState=0 should be ignored."""
        from jazira_app.dahua.api import _process_event
        
        event = {
            "Code": "AccessControl",
            "DataSource": "Offline",
            "Data": {
                "UserID": "777",
                "AttendanceState": 0,
                "UTC": 1706745600,
                "RecNo": 1
            }
        }
        result = _process_event(event, "TEST123")
        self.assertFalse(result)
    
    def test_tc03_unknown_employee_ignored(self):
        """TC-03: Unknown UserID should be ignored."""
        from jazira_app.dahua.api import _process_event
        
        event = {
            "Code": "AccessControl",
            "DataSource": "Offline",
            "Data": {
                "UserID": "99999",
                "AttendanceState": 1,
                "UTC": 1706745600,
                "RecNo": 1
            }
        }
        result = _process_event(event, "TEST123")
        self.assertFalse(result)
    
    def test_tc04_unmapped_device_ignored(self):
        """TC-04: Unmapped device SN should be ignored."""
        from jazira_app.dahua.api import _process_event
        
        event = {
            "Code": "AccessControl",
            "DataSource": "Offline",
            "Data": {
                "UserID": "777",
                "AttendanceState": 1,
                "UTC": 1706745600,
                "RecNo": 1
            }
        }
        result = _process_event(event, "UNKNOWN_DEVICE")
        self.assertFalse(result)
    
    def test_tc05_company_mismatch_ignored(self):
        """TC-05: Employee from different company should be ignored."""
        # Create employee in different company
        if not frappe.db.exists("Company", "Other Company"):
            frappe.get_doc({
                "doctype": "Company",
                "company_name": "Other Company",
                "default_currency": "UZS",
                "country": "Uzbekistan"
            }).insert(ignore_permissions=True)
        
        if not frappe.db.exists("Employee", {"employee_id": "888"}):
            frappe.get_doc({
                "doctype": "Employee",
                "employee_name": "Other Employee",
                "employee_id": "888",
                "company": "Other Company",
                "gender": "Male",
                "date_of_birth": "1990-01-01",
                "date_of_joining": "2020-01-01"
            }).insert(ignore_permissions=True)
            frappe.db.commit()
        
        from jazira_app.dahua.api import _process_event
        
        event = {
            "Code": "AccessControl",
            "DataSource": "Offline",
            "Data": {
                "UserID": "888",
                "AttendanceState": 1,
                "UTC": 1706745600,
                "RecNo": 1
            }
        }
        result = _process_event(event, "TEST123")
        self.assertFalse(result)
    
    # =========================================================================
    # Normal IN/OUT Tests
    # =========================================================================
    
    def test_tc06_valid_in_creates_checkin(self):
        """TC-06: Valid IN event creates Employee Checkin."""
        from jazira_app.dahua.api import _process_event
        
        event = {
            "Code": "AccessControl",
            "DataSource": "Offline",
            "Data": {
                "UserID": "777",
                "AttendanceState": 1,
                "UTC": 1706745600,
                "RecNo": 100
            }
        }
        result = _process_event(event, "TEST123")
        self.assertTrue(result)
        
        # Verify checkin was created
        checkin = frappe.get_last_doc("Employee Checkin", {"checkin_source": "Dahua"})
        self.assertEqual(checkin.log_type, "IN")
        self.assertEqual(checkin.checkin_reason, "IN")
        self.assertEqual(checkin.dahua_attendance_state, 1)
    
    def test_tc07_valid_out_creates_checkin(self):
        """TC-07: Valid OUT event creates Employee Checkin."""
        from jazira_app.dahua.api import _process_event
        
        event = {
            "Code": "AccessControl",
            "DataSource": "Offline",
            "Data": {
                "UserID": "777",
                "AttendanceState": 2,
                "UTC": 1706778000,
                "RecNo": 101
            }
        }
        result = _process_event(event, "TEST123")
        self.assertTrue(result)
        
        checkin = frappe.get_last_doc("Employee Checkin", {"checkin_source": "Dahua"})
        self.assertEqual(checkin.log_type, "OUT")
        self.assertEqual(checkin.checkin_reason, "OUT")
    
    def test_tc08_duplicate_ignored(self):
        """TC-08: Duplicate events create only one checkin."""
        from jazira_app.dahua.api import _process_event
        
        event = {
            "Code": "AccessControl",
            "DataSource": "Offline",
            "Data": {
                "UserID": "777",
                "AttendanceState": 1,
                "UTC": 1706745600,
                "RecNo": 200
            }
        }
        
        # Send same event 3 times
        result1 = _process_event(event, "TEST123")
        frappe.db.commit()
        result2 = _process_event(event, "TEST123")
        result3 = _process_event(event, "TEST123")
        
        self.assertTrue(result1)
        self.assertFalse(result2)
        self.assertFalse(result3)
        
        # Verify only 1 checkin exists
        count = frappe.db.count("Employee Checkin", {"checkin_source": "Dahua"})
        self.assertEqual(count, 1)
    
    # =========================================================================
    # Temporary Out/Return Tests
    # =========================================================================
    
    def test_tc09_temp_out_creates_checkin(self):
        """TC-09: TEMP OUT (state 5) creates checkin with OUT log_type."""
        from jazira_app.dahua.api import _process_event
        
        event = {
            "Code": "AccessControl",
            "DataSource": "Offline",
            "Data": {
                "UserID": "777",
                "AttendanceState": 5,
                "UTC": 1706760000,
                "RecNo": 102
            }
        }
        result = _process_event(event, "TEST123")
        self.assertTrue(result)
        
        checkin = frappe.get_last_doc("Employee Checkin", {"checkin_source": "Dahua"})
        self.assertEqual(checkin.log_type, "OUT")
        self.assertEqual(checkin.checkin_reason, "TEMP_OUT")
        self.assertEqual(checkin.dahua_attendance_state, 5)
    
    def test_tc10_return_creates_checkin(self):
        """TC-10: RETURN (state 3) creates checkin with IN log_type."""
        from jazira_app.dahua.api import _process_event
        
        event = {
            "Code": "AccessControl",
            "DataSource": "Offline",
            "Data": {
                "UserID": "777",
                "AttendanceState": 3,
                "UTC": 1706763600,
                "RecNo": 103
            }
        }
        result = _process_event(event, "TEST123")
        self.assertTrue(result)
        
        checkin = frappe.get_last_doc("Employee Checkin", {"checkin_source": "Dahua"})
        self.assertEqual(checkin.log_type, "IN")
        self.assertEqual(checkin.checkin_reason, "RETURN")
        self.assertEqual(checkin.dahua_attendance_state, 3)
    
    def test_tc11_full_shift_sequence(self):
        """TC-11: Full shift with temp break creates 4 correct checkins."""
        from jazira_app.dahua.api import _process_event
        
        # IN at 08:00
        _process_event({
            "Code": "AccessControl",
            "DataSource": "Offline",
            "Data": {"UserID": "777", "AttendanceState": 1, "UTC": 1706770800, "RecNo": 1}
        }, "TEST123")
        
        # TEMP OUT at 12:00
        _process_event({
            "Code": "AccessControl",
            "DataSource": "Offline",
            "Data": {"UserID": "777", "AttendanceState": 5, "UTC": 1706785200, "RecNo": 2}
        }, "TEST123")
        
        # RETURN at 13:00
        _process_event({
            "Code": "AccessControl",
            "DataSource": "Offline",
            "Data": {"UserID": "777", "AttendanceState": 3, "UTC": 1706788800, "RecNo": 3}
        }, "TEST123")
        
        # OUT at 17:00
        _process_event({
            "Code": "AccessControl",
            "DataSource": "Offline",
            "Data": {"UserID": "777", "AttendanceState": 2, "UTC": 1706803200, "RecNo": 4}
        }, "TEST123")
        
        frappe.db.commit()
        
        # Verify 4 checkins created
        checkins = frappe.get_all(
            "Employee Checkin",
            filters={"checkin_source": "Dahua"},
            fields=["log_type", "checkin_reason", "dahua_attendance_state"],
            order_by="time asc"
        )
        
        self.assertEqual(len(checkins), 4)
        
        # Verify sequence
        self.assertEqual(checkins[0].log_type, "IN")
        self.assertEqual(checkins[0].checkin_reason, "IN")
        
        self.assertEqual(checkins[1].log_type, "OUT")
        self.assertEqual(checkins[1].checkin_reason, "TEMP_OUT")
        
        self.assertEqual(checkins[2].log_type, "IN")
        self.assertEqual(checkins[2].checkin_reason, "RETURN")
        
        self.assertEqual(checkins[3].log_type, "OUT")
        self.assertEqual(checkins[3].checkin_reason, "OUT")
    
    # =========================================================================
    # DataSource Tests
    # =========================================================================
    
    def test_tc12_pulse_state1_ignored(self):
        """TC-12: Pulse for state 1 (IN) should be ignored."""
        from jazira_app.dahua.api import _process_event
        
        event = {
            "Code": "AccessControl",
            "DataSource": "Pulse",
            "Data": {
                "UserID": "777",
                "AttendanceState": 1,
                "UTC": 1706745600,
                "BlockId": 1
            }
        }
        result = _process_event(event, "TEST123")
        self.assertFalse(result)
    
    def test_tc13_pulse_state5_accepted(self):
        """TC-13: Pulse for state 5 (TEMP OUT) should be accepted."""
        from jazira_app.dahua.api import _process_event
        
        event = {
            "Code": "AccessControl",
            "DataSource": "Pulse",
            "Data": {
                "UserID": "777",
                "AttendanceState": 5,
                "UTC": 1706760000,
                "BlockId": 1
            }
        }
        result = _process_event(event, "TEST123")
        self.assertTrue(result)
    
    def test_tc14_offline_always_accepted(self):
        """TC-14: Offline events should always be accepted for valid states."""
        from jazira_app.dahua.api import _process_event
        
        event = {
            "Code": "AccessControl",
            "DataSource": "Offline",
            "Data": {
                "UserID": "777",
                "AttendanceState": 1,
                "UTC": 1706745600,
                "RecNo": 300
            }
        }
        result = _process_event(event, "TEST123")
        self.assertTrue(result)
    
    # =========================================================================
    # Time Conversion Test
    # =========================================================================
    
    def test_tc15_utc_epoch_converted(self):
        """TC-15: UTC epoch timestamp should be converted to system timezone."""
        from jazira_app.dahua.api import _convert_epoch_to_local
        
        # 2024-02-01 00:00:00 UTC
        epoch = 1706745600
        
        local_dt = _convert_epoch_to_local(epoch)
        
        # Should be a datetime object
        self.assertIsInstance(local_dt, datetime)
        
        # Should be naive (no tzinfo)
        self.assertIsNone(local_dt.tzinfo)
    
    # =========================================================================
    # Helper Function Tests
    # =========================================================================
    
    def test_event_id_generation_offline(self):
        """Event ID for Offline should use RecNo."""
        from jazira_app.dahua.api import _generate_event_id
        
        data = {"UserID": "777", "RecNo": 12345}
        event_id = _generate_event_id("SN123", data, "Offline", 1)
        
        self.assertEqual(event_id, "SN123-R12345-777-1")
    
    def test_event_id_generation_pulse(self):
        """Event ID for Pulse should use BlockId."""
        from jazira_app.dahua.api import _generate_event_id
        
        data = {"UserID": "777", "BlockId": 5}
        event_id = _generate_event_id("SN123", data, "Pulse", 5)
        
        self.assertEqual(event_id, "SN123-B5-777-5")
    
    def test_employee_resolution_by_employee_id(self):
        """Employee should be resolved by employee_id field."""
        from jazira_app.dahua.api import _resolve_employee
        
        employee = _resolve_employee("777", "Test Jazira Sub")
        self.assertIsNotNone(employee)
    
    def test_employee_resolution_wrong_company(self):
        """Employee resolution should fail for wrong company."""
        from jazira_app.dahua.api import _resolve_employee
        
        employee = _resolve_employee("777", "Wrong Company")
        self.assertIsNone(employee)
