"""Provider-neutral manual shipment tracking workflow."""
from __future__ import annotations

import frappe
from frappe.utils import convert_utc_to_system_timezone, get_datetime, now_datetime

from shipment_tracking.notifications import notify_shipment_status_transition
from shipment_tracking.services.shipments import mirror_summary_fields
from shipment_tracking.services.statuses import dedupe_event_key, normalize_tracking_status, safe_json


def site_datetime(value):
    if not value:
        return None
    parsed = get_datetime(value)
    if parsed and parsed.tzinfo is not None:
        parsed = convert_utc_to_system_timezone(parsed).replace(tzinfo=None)
    return parsed


def sync_timeline(shipment, timeline_rows):
    existing = {
        dedupe_event_key({
            "date_time": row.date_time,
            "status": row.status,
            "detail": row.detail,
            "location": row.location,
        })
        for row in shipment.events or []
    }
    added = 0
    for source in timeline_rows or []:
        row = {
            "date_time": site_datetime(source.get("date_time")),
            "status": source.get("status"),
            "detail": source.get("detail"),
            "location": source.get("location"),
        }
        key = dedupe_event_key(row)
        if key in existing:
            continue
        shipment.append("events", row)
        existing.add(key)
        added += 1
    return added


def apply_tracking_data(shipment, data, stored_response):
    previous_status = normalize_tracking_status(
        shipment.normalized_status or shipment.shipkia_status
    )
    incoming_time = site_datetime(data.get("status_time"))
    last_synced = site_datetime(shipment.last_synced_on)
    stale = bool(incoming_time and last_synced and incoming_time < last_synced)

    sync_timeline(shipment, data.get("timeline") or [])

    if not stale:
        assignments = {
            "company": data.get("company"),
            "company_id": data.get("company_id"),
            "shipkia_tracking_id": data.get("tracking_id"),
            "shipkia_awb_number": data.get("awb"),
            "shipkia_stage": data.get("stage"),
            "shipkia_status": data.get("status"),
            "shipkia_status_detail": data.get("status_detail"),
            "payment_mode": data.get("payment_mode"),
            "delivery_partner": data.get("courier_partner"),
            "courier_partner_mode": data.get("courier_mode"),
            "delivery_location": data.get("delivery_location"),
        }
        for fieldname, value in assignments.items():
            if value not in (None, ""):
                shipment.set(fieldname, value)

        if data.get("estimated_delivery"):
            shipment.shipkia_estimated_delivery = site_datetime(data["estimated_delivery"])
        if data.get("delivered_on"):
            shipment.shipkia_delivered_on = site_datetime(data["delivered_on"])
        shipment.normalized_status = normalize_tracking_status(shipment.shipkia_status)
        shipment.last_synced_on = incoming_time or now_datetime()

    shipment.raw_latest_response = safe_json(stored_response)
    shipment.save(ignore_permissions=True)
    mirror_summary_fields(
        shipment,
        sales_invoice=shipment.sales_invoice,
        encounter_name=shipment.patient_encounter,
    )
    if not stale:
        notify_shipment_status_transition(shipment, previous_status)
    return stale


def _failure_message(response):
    status = getattr(response, "status_code", 0)
    if status in (401, 403):
        return "Shipkia rejected the account API key."
    if status == 404:
        return "Shipkia tracking record was not found."
    if status == 429:
        return "Shipkia tracking rate limit was reached. Retry later."
    if status >= 500:
        return "Shipkia tracking service is temporarily unavailable."
    return "Shipkia tracking sync failed. Check Shipment Tracking Sync Log."


def run(shipment, account, adapter):
    if not shipment.shipkia_order_id:
        frappe.throw("Shipment has no Shipkia Order ID.")
    if not account.allow_existing_operations:
        frappe.throw("Existing operations are disabled for this Shipkia account.")
    if not account.enable_manual_tracking_refresh:
        frappe.throw("Tracking is disabled for this Shipkia account.")
    if not account.order_tracking_url:
        frappe.throw("Configure the Order Tracking URL for this Shipkia account.")

    lock_key = "shipkia:tracking:" + shipment.name
    with frappe.cache().lock(lock_key, timeout=120, blocking_timeout=10):
        shipment.reload()
        request_data = adapter.build_request(shipment, account)
        log = frappe.get_doc({
            "doctype": "Shipment Tracking Sync Log",
            "direction": "Outbound",
            "action": "Track Shipment",
            "reference_doctype": "Shipment Tracking Shipment",
            "reference_name": shipment.name,
            "shipkia_order_id": shipment.shipkia_order_id,
            "shipkia_account": account.name,
            "request_json": safe_json(request_data),
            "status": "Running",
        }).insert(ignore_permissions=True)

        try:
            response, body = adapter.send(account, request_data)
        except Exception:
            log.status = "Failed"
            log.error_message = "Unable to reach the shipping service. Please retry later."
            log.save(ignore_permissions=True)
            frappe.db.commit()
            frappe.throw(log.error_message)

        stored_response = adapter.response_for_storage(body)
        log.http_status = response.status_code
        log.response_json = safe_json(stored_response)
        if response.status_code not in (200, 201, 202):
            log.status = "Failed"
            log.error_message = _failure_message(response)
            log.save(ignore_permissions=True)
            frappe.db.commit()
            frappe.throw(log.error_message)

        try:
            data = adapter.parse_response(body, shipment)
            stale = apply_tracking_data(shipment, data, stored_response)
        except Exception as error:
            log.status = "Failed"
            log.error_message = str(error)
            log.save(ignore_permissions=True)
            frappe.db.commit()
            frappe.throw(str(error))

        log.status = "Success"
        if stale:
            log.reconciliation_note = "Provider response was older than the saved shipment summary; history was synchronized without regressing the current status."
        log.save(ignore_permissions=True)
        return {
            "success": True,
            "shipment": shipment.name,
            "account": account.name,
            "order_id": shipment.shipkia_order_id,
            "tracking_id": shipment.shipkia_tracking_id,
            "awb": shipment.shipkia_awb_number,
            "stage": shipment.shipkia_stage,
            "status": shipment.shipkia_status,
            "courier": shipment.delivery_partner,
            "courier_mode": shipment.courier_partner_mode,
            "last_updated": shipment.last_synced_on,
            "stale": stale,
            "message": "Shipment tracking updated.",
        }


CHECK_TTL_SECONDS = 300
COMPARISON_FIELDS = (
    ("stage", "Stage", "shipkia_stage"),
    ("status", "Status", "shipkia_status"),
    ("courier_partner", "Courier", "delivery_partner"),
    ("courier_mode", "Mode", "courier_partner_mode"),
    ("status_time", "Last Updated", "last_synced_on"),
)


def _tracking_summary(shipment, data=None):
    data = data or {}
    return {
        "shipment": shipment.name,
        "order_id": shipment.shipkia_order_id,
        "awb": data.get("awb") or shipment.shipkia_awb_number,
        "stage": data.get("stage") or shipment.shipkia_stage,
        "status": data.get("status") or shipment.shipkia_status,
        "courier": data.get("courier_partner") or shipment.delivery_partner,
        "courier_mode": data.get("courier_mode") or shipment.courier_partner_mode,
        "last_updated": site_datetime(data.get("status_time")) or shipment.last_synced_on,
    }


def _display_value(value, datetime_field=False):
    if value in (None, ""):
        return "-"
    return site_datetime(value) if datetime_field else value


def _same_value(left, right, datetime_field=False):
    if datetime_field:
        return site_datetime(left) == site_datetime(right)
    return str(left or "").strip().casefold() == str(right or "").strip().casefold()


def compare_tracking_data(shipment, data):
    changes = []
    for provider_field, label, shipment_field in COMPARISON_FIELDS:
        provider_value = data.get(provider_field)
        if provider_value in (None, ""):
            continue
        current_value = getattr(shipment, shipment_field, None)
        if _same_value(
            current_value,
            provider_value,
            datetime_field=provider_field == "status_time",
        ):
            continue
        changes.append({
            "field": provider_field,
            "label": label,
            "erpnext": _display_value(current_value, provider_field == "status_time"),
            "shipkia": _display_value(provider_value, provider_field == "status_time"),
        })

    identity_changed = any(
        provider_value not in (None, "")
        and not _same_value(current_value, provider_value)
        for current_value, provider_value in (
            (shipment.shipkia_awb_number, data.get("awb")),
            (shipment.shipkia_tracking_id, data.get("tracking_id")),
        )
    )
    incoming_time = site_datetime(data.get("status_time"))
    saved_time = site_datetime(shipment.last_synced_on)
    provider_older = bool(incoming_time and saved_time and incoming_time < saved_time)
    if provider_older:
        changes = []
        identity_changed = False
    return changes, identity_changed, provider_older


def _validate_tracking_operation(shipment, account):
    if not shipment.shipkia_order_id:
        frappe.throw("Shipment has no Shipkia Order ID.")
    if not account.allow_existing_operations:
        frappe.throw("Existing operations are disabled for this Shipkia account.")
    if not account.enable_manual_tracking_refresh:
        frappe.throw("Tracking is disabled for this Shipkia account.")
    if not account.order_tracking_url:
        frappe.throw("Configure the Order Tracking URL for this Shipkia account.")


def check_for_updates(shipment, account, adapter):
    _validate_tracking_operation(shipment, account)
    lock_key = "shipkia:tracking:" + shipment.name
    with frappe.cache().lock(lock_key, timeout=120, blocking_timeout=10):
        shipment.reload()
        request_data = adapter.build_request(shipment, account)
        log = frappe.get_doc({
            "doctype": "Shipment Tracking Sync Log",
            "direction": "Outbound",
            "action": "Check Shipment Tracking",
            "reference_doctype": "Shipment Tracking Shipment",
            "reference_name": shipment.name,
            "shipkia_order_id": shipment.shipkia_order_id,
            "shipkia_account": account.name,
            "request_json": safe_json(request_data),
            "status": "Running",
        }).insert(ignore_permissions=True)
        try:
            response, body = adapter.send(account, request_data)
        except Exception:
            log.status = "Failed"
            log.error_message = "Unable to reach the shipping service. Please retry later."
            log.save(ignore_permissions=True)
            frappe.db.commit()
            frappe.throw(log.error_message)

        stored_response = adapter.response_for_storage(body)
        log.http_status = response.status_code
        log.response_json = safe_json(stored_response)
        if response.status_code not in (200, 201, 202):
            log.status = "Failed"
            log.error_message = _failure_message(response)
            log.save(ignore_permissions=True)
            frappe.db.commit()
            frappe.throw(log.error_message)

        try:
            data = adapter.parse_response(body, shipment)
            changes, identity_changed, provider_older = compare_tracking_data(
                shipment,
                data,
            )
        except Exception as error:
            log.status = "Failed"
            log.error_message = str(error)
            log.save(ignore_permissions=True)
            frappe.db.commit()
            frappe.throw(str(error))

        update_available = bool(changes or identity_changed)
        token = None
        if update_available:
            token = frappe.generate_hash(length=40)
            cache_payload = {
                "user": frappe.session.user,
                "shipment": shipment.name,
                "account": account.name,
                "data": data,
                "stored_response": stored_response,
                "check_log": log.name,
            }
            frappe.cache().set_value(
                "shipkia:tracking-check:" + token,
                safe_json(cache_payload),
                expires_in_sec=CHECK_TTL_SECONDS,
            )

        log.status = "Success"
        if provider_older:
            log.reconciliation_note = "ERPNext already contains newer shipment information than the provider response."
        elif update_available:
            log.reconciliation_note = "Shipkia update available; awaiting user confirmation."
        else:
            log.reconciliation_note = "ERPNext already matches Shipkia."
        log.save(ignore_permissions=True)
        return {
            "success": True,
            "matches": not update_available,
            "update_available": update_available,
            "provider_older": provider_older,
            "check_token": token,
            "summary": _tracking_summary(shipment, data),
            "changes": changes,
            "identity_changed": identity_changed,
            "message": (
                "Shipkia has newer tracking information."
                if update_available
                else "ERPNext already matches the latest Shipkia tracking details."
            ),
        }


def apply_checked_update(check_token):
    import json

    cache_key = "shipkia:tracking-check:" + str(check_token or "")
    cached = frappe.cache().get_value(cache_key)
    if not cached:
        frappe.throw("This tracking check has expired. Check Shipkia again.")
    if isinstance(cached, bytes):
        cached = cached.decode()
    payload = json.loads(cached) if isinstance(cached, str) else cached
    if payload.get("user") != frappe.session.user:
        frappe.throw("This tracking check belongs to another user.")

    shipment = frappe.get_doc("Shipment Tracking Shipment", payload["shipment"])
    shipment.check_permission("read")
    shipment.check_permission("write")
    account = frappe.get_doc("Shipkia Account", payload["account"])
    _validate_tracking_operation(shipment, account)
    lock_key = "shipkia:tracking:" + shipment.name
    with frappe.cache().lock(lock_key, timeout=120, blocking_timeout=10):
        shipment.reload()
        changes, identity_changed, provider_older = compare_tracking_data(
            shipment,
            payload["data"],
        )
        if provider_older:
            frappe.cache().delete_value(cache_key)
            return {
                **_tracking_summary(shipment),
                "success": True,
                "updated": False,
                "message": "ERPNext already contains newer shipment information.",
            }
        if not changes and not identity_changed:
            frappe.cache().delete_value(cache_key)
            return {
                **_tracking_summary(shipment),
                "success": True,
                "updated": False,
                "message": "ERPNext already matches the latest Shipkia tracking details.",
            }

        stale = apply_tracking_data(
            shipment,
            payload["data"],
            payload["stored_response"],
        )
        log = frappe.get_doc({
            "doctype": "Shipment Tracking Sync Log",
            "direction": "Outbound",
            "action": "Apply Shipment Tracking",
            "reference_doctype": "Shipment Tracking Shipment",
            "reference_name": shipment.name,
            "shipkia_order_id": shipment.shipkia_order_id,
            "shipkia_account": account.name,
            "http_status": 200,
            "request_json": safe_json({
                "check_log": payload.get("check_log"),
                "confirmed_fields": [row["field"] for row in changes],
            }),
            "response_json": safe_json(payload["stored_response"]),
            "status": "Success",
            "reconciliation_note": "Applied a user-confirmed Shipkia tracking check.",
        }).insert(ignore_permissions=True)
        frappe.cache().delete_value(cache_key)
        return {
            **_tracking_summary(shipment),
            "success": True,
            "updated": not stale,
            "stale": stale,
            "sync_log": log.name,
            "message": (
                "Shipment status updated."
                if not stale
                else "ERPNext already contains newer shipment information."
            ),
        }
