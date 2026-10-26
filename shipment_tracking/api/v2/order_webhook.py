"""Inbound status webhooks for New Shipkia OMS."""
from __future__ import annotations

import hashlib
import hmac

import frappe
from frappe.utils import cint, convert_utc_to_system_timezone, get_datetime, now_datetime

from shipment_tracking.api.webhook_utils import clean, extract_webhook_body, first_clean_value
from shipment_tracking.notifications import notify_shipment_status_transition
from shipment_tracking.services.shipments import mirror_summary_fields
from shipment_tracking.services.statuses import normalize_tracking_status, safe_json


EXPECTED_EVENT = "order_tracking"
EXPECTED_RECORD_EVENTS = {"records_created", "records_updated"}


def request_header(name):
    return clean(frappe.get_request_header(name))


def get_owned_shipment(order_id):
    names = frappe.get_all(
        "Shipment Tracking Shipment",
        filters={"shipkia_order_id": order_id},
        pluck="name",
        limit=2,
    )
    if len(names) != 1:
        frappe.local.response["http_status_code"] = 404
        frappe.throw("Webhook order ownership is missing or ambiguous.")

    settings = frappe.get_single("Shipment Tracking Settings")
    if not settings.default_shipkia_account:
        frappe.local.response["http_status_code"] = 409
        frappe.throw("Choose the default Shipkia Account in Shipment Tracking Settings.")
    gateway_account = frappe.get_doc("Shipkia Account", settings.default_shipkia_account)
    if gateway_account.platform != "New OMS":
        frappe.local.response["http_status_code"] = 409
        frappe.throw("The default Shipkia Account must use the New OMS platform.")

    # The default New OMS account authenticates the shared inbound webhook. The
    # shipment owner remains authoritative for tracking, support, and audit logs.
    shipment = frappe.get_doc("Shipment Tracking Shipment", names[0])
    owner_account = frappe.get_doc("Shipkia Account", shipment.shipkia_account)
    if not cint(owner_account.allow_existing_operations):
        frappe.local.response["http_status_code"] = 409
        frappe.throw("Existing operations are disabled for this shipment account.")
    return shipment, owner_account, gateway_account


def authenticate(account):
    if not cint(account.enable_webhook_security):
        frappe.local.response["http_status_code"] = 403
        frappe.throw("Webhook security is not enabled for this Shipkia account.", frappe.PermissionError)
    expected = account.get_password("webhook_secret", raise_exception=False) or ""
    supplied = request_header("X-Webhook-Secret") or ""
    if not expected or not hmac.compare_digest(str(expected), str(supplied)):
        frappe.local.response["http_status_code"] = 403
        frappe.throw("Unauthorized request", frappe.PermissionError)


def validate_event_headers():
    event = request_header("X-Shipkia-Event")
    record_event = request_header("X-Shipkia-Record-Event")
    if event != EXPECTED_EVENT:
        frappe.local.response["http_status_code"] = 400
        frappe.throw("Unsupported Shipkia webhook event.")
    if record_event not in EXPECTED_RECORD_EVENTS:
        frappe.local.response["http_status_code"] = 400
        frappe.throw("Unsupported Shipkia record event.")


def site_datetime(value):
    parsed = get_datetime(value)
    if parsed and parsed.tzinfo is not None:
        parsed = convert_utc_to_system_timezone(parsed).replace(tzinfo=None)
    return parsed


def status_time_from(data):
    value = first_clean_value(data, "status_time")
    if not value:
        return now_datetime()
    try:
        return site_datetime(value)
    except Exception:
        frappe.local.response["http_status_code"] = 400
        frappe.throw("Invalid status_time in Shipkia webhook payload.")


def is_stale_event(shipment, status_time):
    last_synced_on = site_datetime(shipment.last_synced_on) if shipment.last_synced_on else None
    return bool(last_synced_on and status_time < last_synced_on)


def apply_status(shipment, data, status_time=None):
    previous_status = shipment.normalized_status or shipment.shipkia_status
    status = first_clean_value(data, "status", "order_status", "shipkia_status")
    stage = first_clean_value(data, "stage", "order_stage", "shipkia_stage")
    awb = first_clean_value(data, "awb", "awb_number")
    courier = first_clean_value(data, "courier_partner", "delivery_partner", "courier")
    courier_mode = first_clean_value(data, "courier_partner_mode")
    instructions = first_clean_value(data, "instructions")
    status_time = status_time or status_time_from(data)

    if status:
        shipment.shipkia_status = status
        shipment.normalized_status = normalize_tracking_status(status)
    if stage:
        shipment.shipkia_stage = stage
    if awb:
        shipment.shipkia_awb_number = awb
    if courier:
        shipment.delivery_partner = courier
    if courier_mode:
        shipment.courier_partner_mode = courier_mode
    if instructions:
        shipment.shipkia_status_detail = instructions
    if shipment.normalized_status == "Delivered" and not shipment.shipkia_delivered_on:
        shipment.shipkia_delivered_on = status_time
    shipment.last_synced_on = status_time

    shipment.append("events", {
        "date_time": status_time,
        "status": status or stage or "Updated",
        "detail": instructions or "Updated via New OMS webhook",
        "location": courier_mode or courier or "",
    })
    return previous_status


def create_sync_log(shipment, account, order_id, event_id, data, response=None):
    return frappe.get_doc({
        "doctype": "Shipment Tracking Sync Log",
        "direction": "Inbound",
        "action": "Order Status Webhook",
        "reference_doctype": "Shipment Tracking Shipment",
        "reference_name": shipment.name,
        "shipkia_order_id": order_id,
        "shipkia_account": account.name,
        "provider_event_id": event_id,
        "http_status": 200,
        "status": "Success",
        "request_json": safe_json({
            "event": request_header("X-Shipkia-Event"),
            "record_event": request_header("X-Shipkia-Record-Event"),
            "body": data,
        }),
        "response_json": safe_json(response) if response else None,
    }).insert(ignore_permissions=True)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def order_status_update():
    payload = frappe.request.get_json() or {}
    data = extract_webhook_body(payload)
    order_id = clean(data.get("order_id"))
    event_id = request_header("X-Shipkia-Event-Id")
    if not order_id:
        frappe.local.response["http_status_code"] = 400
        return {"success": False, "message": "order_id is required"}
    if not event_id:
        frappe.local.response["http_status_code"] = 400
        return {"success": False, "message": "X-Shipkia-Event-Id is required"}

    shipment, owner_account, gateway_account = get_owned_shipment(order_id)
    authenticate(gateway_account)
    validate_event_headers()

    lock_key = "shipkia:webhook:" + hashlib.sha256(order_id.encode()).hexdigest()
    with frappe.cache().lock(lock_key, timeout=60, blocking_timeout=10):
        existing = frappe.db.get_value(
            "Shipment Tracking Sync Log",
            {"provider_event_id": event_id},
            "name",
        )
        if existing:
            return {
                "success": True,
                "duplicate": True,
                "message": f"Event already processed for order {order_id}",
            }

        shipment.reload()
        status_time = status_time_from(data)
        if is_stale_event(shipment, status_time):
            result = {
                "success": True,
                "ignored": True,
                "stale": True,
                "message": f"Older event ignored for order {order_id}",
            }
            log = create_sync_log(shipment, owner_account, order_id, event_id, data, result)
            result["log"] = log.name
            frappe.db.commit()
            return result

        previous_status = apply_status(shipment, data, status_time=status_time)
        shipment.raw_latest_response = safe_json(data)
        shipment.save(ignore_permissions=True)
        mirror_summary_fields(
            shipment,
            sales_invoice=shipment.sales_invoice,
            encounter_name=shipment.patient_encounter,
        )

        log = create_sync_log(shipment, owner_account, order_id, event_id, data)
        notify_shipment_status_transition(shipment, previous_status)
        frappe.db.commit()
        return {
            "success": True,
            "message": f"Shipment updated for order {order_id}",
            "shipment": shipment.name,
            "log": log.name,
        }
