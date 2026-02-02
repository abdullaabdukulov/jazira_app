"""
Dahua Access Control Webhook API for ERPNext HRMS

Endpoint: /api/method/jazira_app.dahua.api.receive_event

This module handles webhook events from Dahua access control devices and creates
Employee Checkin records in ERPNext HRMS. It supports:
- Standard IN/OUT (AttendanceState 1, 2)
- Temporary OUT/RETURN (AttendanceState 5, 3)
- Dual-layer deduplication (Redis + DB unique constraint)
- Multi-company device mapping
"""

import frappe
from frappe import _
from datetime import datetime
import pytz


# =============================================================================
# CONSTANTS
# =============================================================================

# AttendanceState -> (log_type, checkin_reason) mapping
# States 3 and 5 use standard IN/OUT log_type so Shift Auto Attendance works
# The checkin_reason field preserves semantic meaning for reporting
STATE_MAPPING = {
    1: {"log_type": "IN", "reason": "IN"},        # Normal check-in (start work)
    2: {"log_type": "OUT", "reason": "OUT"},      # Normal check-out (end work)
    3: {"log_type": "IN", "reason": "RETURN"},    # Return from temporary break
    5: {"log_type": "OUT", "reason": "TEMP_OUT"}, # Temporary exit during shift
}

VALID_STATES = frozenset({1, 2, 3, 5})
TEMP_STATES = frozenset({3, 5})  # States accepted via Pulse (not just Offline)

# Redis cache settings
CACHE_PREFIX = "dahua:event:"
CACHE_TTL = 120  # seconds


# =============================================================================
# DEBUG LOGGING (set to False in production)
# =============================================================================

DEBUG_MODE = True  # Set to False in production

def _debug_log(message: str):
    """Log debug message if DEBUG_MODE is enabled."""
    if DEBUG_MODE:
        frappe.logger().info(f"[DAHUA DEBUG] {message}")
        print(f"[DAHUA DEBUG] {message}")


# =============================================================================
# MAIN WEBHOOK ENDPOINT
# =============================================================================

@frappe.whitelist(allow_guest=True)
def receive_event():
    """
    Main webhook endpoint for Dahua Access Control events.
    
    ACTUAL Dahua payload structure (confirmed from device):
    {
        "Action": "Pulse",
        "Code": "AccessControl",
        "Data": {
            "SN": "BE0FE78PAJD287F",
            "UserID": "777",
            "AttendanceState": 1,
            "UTC": 1769972634,
            "BlockId": 26128,
            "CardName": "Abdulla",
            ...
        },
        "Index": 0
    }
    
    Returns:
        HTTP 200: Event processed successfully
        HTTP 202: Event intentionally ignored (filtered)
        HTTP 400: Invalid JSON
        HTTP 401: Invalid secret (if configured)
        HTTP 500: Server error
    """
    # Optional secret validation
    if not _validate_secret():
        frappe.local.response.http_status_code = 401
        return {"error": "Unauthorized"}
    
    # Parse JSON payload
    try:
        data = frappe.request.get_json(force=True)
    except Exception as e:
        frappe.local.response.http_status_code = 400
        return {"error": "Invalid JSON", "detail": str(e)}
    
    if not data:
        frappe.local.response.http_status_code = 400
        return {"error": "Empty payload"}
    
    _debug_log(f"Raw payload: {data}")
    
    # Process the single event (Dahua sends one event per request)
    try:
        result = _process_event(data)
        if result:
            frappe.db.commit()
            return {"status": "processed", "message": "Checkin created"}
        else:
            frappe.local.response.http_status_code = 202
            return {"status": "ignored"}
    except Exception as e:
        frappe.log_error(
            title="Dahua Event Processing Error",
            message=f"Payload: {data}\nError: {str(e)}"
        )
        frappe.local.response.http_status_code = 500
        return {"error": str(e)}


# =============================================================================
# EVENT PROCESSING
# =============================================================================

def _process_event(data: dict) -> bool:
    """
    Process a single Dahua event.
    
    Args:
        data: Full webhook payload
        
    Returns:
        True if Employee Checkin created, False if event was filtered/ignored
    """
    # Filter 1: Code must be "AccessControl"
    code = data.get("Code", "")
    if code != "AccessControl":
        _debug_log(f"REJECTED: Code is '{code}', expected 'AccessControl'")
        return False
    
    # Get Data block
    event_data = data.get("Data", {})
    if not event_data:
        _debug_log("REJECTED: No 'Data' in payload")
        return False
    
    # Extract key fields
    device_sn = event_data.get("SN", "")
    attendance_state = event_data.get("AttendanceState")
    action = data.get("Action", "")  # "Pulse" or could indicate Offline
    
    _debug_log(f"Event: SN={device_sn}, AttendanceState={attendance_state}, Action={action}")
    
    # Filter 2: Must be a valid AttendanceState
    if attendance_state not in VALID_STATES:
        _debug_log(f"REJECTED: AttendanceState {attendance_state} not in {VALID_STATES}")
        return False
    
    # Filter 3: For Pulse events, only accept TEMP states (3, 5) for normal IN/OUT
    # NOTE: Based on observed data, device sends Pulse for all events
    # We'll accept all valid states from Pulse since that's what the device sends
    # If Offline events are also sent later, deduplication will handle it
    
    # Filter 4: Device must be mapped and active
    device = _get_active_device(device_sn)
    if not device:
        _debug_log(f"REJECTED: Device SN '{device_sn}' not found or inactive")
        return False
    
    _debug_log(f"Device found: {device}")
    
    # Filter 5: Resolve employee and validate company
    user_id = str(event_data.get("UserID", "")).strip()
    if not user_id:
        _debug_log("REJECTED: No UserID in event")
        return False
    
    employee = _resolve_employee(user_id, device.company)
    if not employee:
        _debug_log(f"REJECTED: Employee not found for UserID '{user_id}' in company '{device.company}'")
        return False
    
    _debug_log(f"Employee resolved: {employee}")
    
    # Generate deterministic event_id for deduplication
    event_id = _generate_event_id(device_sn, event_data, action, attendance_state)
    _debug_log(f"Event ID: {event_id}")
    
    # Check for duplicate (Redis fast path + DB fallback)
    if _is_duplicate(event_id):
        _debug_log(f"REJECTED: Duplicate event {event_id}")
        return False
    
    # Convert UTC epoch to system timezone
    # Pulse events use UTC/RealUTC, Offline events use CreateTimeRealUTC/CreateTime
    epoch = (
        event_data.get("UTC") or 
        event_data.get("RealUTC") or 
        event_data.get("CreateTimeRealUTC") or 
        event_data.get("CreateTime") or 
        0
    )
    if not epoch:
        _debug_log("REJECTED: No timestamp in event (checked UTC, RealUTC, CreateTimeRealUTC, CreateTime)")
        return False
    
    checkin_time = _convert_epoch_to_local(epoch)
    _debug_log(f"Checkin time: {checkin_time}")
    
    # Get log_type and reason from mapping
    mapping = STATE_MAPPING[attendance_state]
    
    # Create Employee Checkin
    try:
        _create_checkin(
            employee=employee,
            time=checkin_time,
            log_type=mapping["log_type"],
            device_id=device_sn,
            event_id=event_id,
            attendance_state=attendance_state,
            reason=mapping["reason"]
        )
        _mark_processed(event_id)
        _debug_log(f"SUCCESS: Created checkin for {employee}, log_type={mapping['log_type']}, reason={mapping['reason']}")
        return True
    except frappe.DuplicateEntryError:
        # Race condition: record already created by another request
        _mark_processed(event_id)
        _debug_log(f"DUPLICATE: Checkin already exists for event {event_id}")
        return False
    except Exception as e:
        frappe.log_error(
            title="Dahua Checkin Creation Error",
            message=f"Employee: {employee}\nEvent ID: {event_id}\nError: {str(e)}"
        )
        raise


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _validate_secret() -> bool:
    """
    Validate optional shared secret from request header or body.
    
    Configure in site_config.json:
        "dahua_webhook_secret": "your-secure-random-string"
    
    Returns:
        True if secret is valid or not configured
    """
    expected = frappe.conf.get("dahua_webhook_secret")
    if not expected:
        return True  # No secret configured, allow all
    
    # Check header first (preferred)
    provided = frappe.request.headers.get("X-DAHUA-SECRET")
    
    # Fallback to query string
    if not provided:
        provided = frappe.form_dict.get("secret")
    
    # Fallback to JSON body
    if not provided:
        try:
            body = frappe.request.get_json(silent=True, force=True) or {}
            provided = body.get("secret")
        except Exception:
            pass
    
    return provided == expected


def _get_active_device(sn: str):
    """
    Get device record if it exists and is active.
    
    Args:
        sn: Device serial number
        
    Returns:
        Dict with name and company, or None if not found/inactive
    """
    if not sn:
        return None
    
    return frappe.db.get_value(
        "Dahua Device",
        {"device_sn": sn, "is_active": 1},
        ["name", "company"],
        as_dict=True
    )


def _resolve_employee(user_id: str, device_company: str) -> str | None:
    """
    Resolve Dahua UserID to ERPNext Employee.
    
    Resolution priority:
    1. Employee.name == user_id (direct document name match)
    2. Employee.attendance_device_id == user_id (standard HRMS field in Attendance & Leaves tab)
    
    Args:
        user_id: UserID from Dahua device
        device_company: Company the device is mapped to
        
    Returns:
        Employee name if found and company matches, else None
    """
    # Priority 1: Direct name match (e.g., user_id = "HR-EMP-00001")
    if frappe.db.exists("Employee", user_id):
        emp_company = frappe.db.get_value("Employee", user_id, "company")
        if emp_company == device_company:
            _debug_log(f"Employee matched by name: {user_id}")
            return user_id
        _debug_log(f"Employee {user_id} found but company mismatch: {emp_company} != {device_company}")
        return None
    
    # Priority 2: Standard HRMS attendance_device_id field (Attendance & Leaves tab)
    emp_name = frappe.db.get_value(
        "Employee",
        {"attendance_device_id": user_id, "company": device_company},
        "name"
    )
    if emp_name:
        _debug_log(f"Employee matched by attendance_device_id: {emp_name}")
        return emp_name
    
    _debug_log(f"No employee found for UserID '{user_id}' in company '{device_company}'")
    return None


def _generate_event_id(sn: str, data: dict, action: str, state: int) -> str:
    """
    Generate deterministic event ID for deduplication.
    
    Format: {sn}-{BlockId}-{UserID}-{state}
    
    Args:
        sn: Device serial number
        data: Event data dictionary
        action: Action type (Pulse, etc.)
        state: AttendanceState
        
    Returns:
        Unique event identifier string
    """
    user_id = str(data.get("UserID", ""))
    block_id = str(data.get("BlockId", "0"))
    
    return f"{sn}-{block_id}-{user_id}-{state}"


def _is_duplicate(event_id: str) -> bool:
    """
    Check if event was already processed using dual-layer deduplication.
    
    Layer 1: Redis cache (fast, short-lived)
    Layer 2: Database unique constraint (persistent)
    
    Args:
        event_id: Unique event identifier
        
    Returns:
        True if duplicate, False if new event
    """
    cache_key = f"{CACHE_PREFIX}{event_id}"
    
    # Fast path: Check Redis
    if frappe.cache().get(cache_key):
        return True
    
    # Slow path: Check database
    if frappe.db.exists("Employee Checkin", {"dahua_event_id": event_id}):
        # Refresh cache to speed future checks
        frappe.cache().set(cache_key, "1", ex=CACHE_TTL)
        return True
    
    return False


def _mark_processed(event_id: str):
    """Mark event as processed in Redis cache."""
    cache_key = f"{CACHE_PREFIX}{event_id}"
    frappe.cache().set(cache_key, "1", ex=CACHE_TTL)


def _convert_epoch_to_local(epoch: int) -> datetime:
    """
    Convert Unix epoch (UTC) to ERPNext system timezone.
    
    Args:
        epoch: Unix timestamp in seconds (UTC)
        
    Returns:
        Naive datetime in system timezone for ERPNext storage
    """
    # Get system timezone from ERPNext settings
    system_tz_name = frappe.db.get_single_value("System Settings", "time_zone") or "UTC"
    
    # Convert epoch to UTC datetime
    utc_dt = datetime.utcfromtimestamp(epoch)
    utc_dt = pytz.UTC.localize(utc_dt)
    
    # Convert to system timezone
    system_tz = pytz.timezone(system_tz_name)
    local_dt = utc_dt.astimezone(system_tz)
    
    # Return naive datetime (ERPNext expects this)
    return local_dt.replace(tzinfo=None)


def _create_checkin(
    employee: str,
    time: datetime,
    log_type: str,
    device_id: str,
    event_id: str,
    attendance_state: int,
    reason: str
):
    """
    Create Employee Checkin record.
    
    Args:
        employee: Employee name/ID
        time: Checkin datetime (naive, in system timezone)
        log_type: "IN" or "OUT"
        device_id: Device serial number
        event_id: Unique event ID for deduplication
        attendance_state: Original Dahua state (1,2,3,5)
        reason: Semantic reason (IN, OUT, TEMP_OUT, RETURN)
    """
    doc = frappe.get_doc({
        "doctype": "Employee Checkin",
        "employee": employee,
        "time": time,
        "log_type": log_type,
        "device_id": device_id,
        "dahua_event_id": event_id,
        "dahua_attendance_state": attendance_state,
        "checkin_source": "Dahua",
        "checkin_reason": reason
    })
    doc.flags.ignore_permissions = True
    doc.insert()


# =============================================================================
# UTILITY FUNCTIONS (for testing/debugging)
# =============================================================================

@frappe.whitelist()
def test_device_mapping(device_sn: str) -> dict:
    """Test if a device SN is properly mapped. For debugging."""
    device = _get_active_device(device_sn)
    if device:
        return {"status": "found", "device": device}
    return {"status": "not_found"}


@frappe.whitelist()
def test_employee_resolution(user_id: str, company: str) -> dict:
    """Test employee resolution. For debugging."""
    employee = _resolve_employee(user_id, company)
    if employee:
        return {"status": "found", "employee": employee}
    return {"status": "not_found"}