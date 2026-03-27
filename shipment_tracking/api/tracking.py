from __future__ import annotations

import frappe
import requests

from .utils import (
    ACTIVE_SYNC_DEFAULT_LIMIT,
    TERMINAL_STATUSES,
    as_datetime,
    dedupe_event_key,
    get_settings,
    latest_timeline_entry,
    make_auth_headers,
    normalize_tracking_status,
    safe_json,
    safe_response_json,
    tracking_result,
    update_doc_if_exists,
)


@frappe.whitelist()
def sync_tracking_for_shipment(shipment_name: str):
    shipment = frappe.get_doc("Shipment Tracking Shipment", shipment_name)
    if not shipment.shipkia_order_id:
        frappe.throw("Shipment has no Shipkia Order ID.")
    return sync_tracking_by_order_id(shipment.shipkia_order_id)


@frappe.whitelist()
def sync_tracking_for_invoice(invoice_name: str):
    shipment_name = frappe.db.get_value("Shipment Tracking Shipment", {"sales_invoice": invoice_name}, "name")
    if not shipment_name:
        frappe.throw("No shipment record linked to this Sales Invoice.")
    return sync_tracking_for_shipment(shipment_name)


@frappe.whitelist()
def sync_tracking_by_order_id(order_id: str):
    shipment_name = frappe.db.get_value("Shipment Tracking Shipment", {"shipkia_order_id": order_id}, "name")
    if not shipment_name:
        frappe.throw("No shipment record found for this Shipkia Order ID.")

    shipment = frappe.get_doc("Shipment Tracking Shipment", shipment_name)
    settings = get_settings()
    if not settings.enabled:
        frappe.throw("Shipment Tracking is disabled in settings.")

    payload = {"order_id": shipment.shipkia_order_id}
    log = frappe.get_doc(
        {
            "doctype": "Shipment Tracking Sync Log",
            "direction": "Outbound",
            "action": "Track Shipment",
            "reference_doctype": "Shipment Tracking Shipment",
            "reference_name": shipment.name,
            "shipkia_order_id": shipment.shipkia_order_id,
            "request_json": safe_json(payload),
            "status": "Running",
        }
    ).insert(ignore_permissions=True)

    try:
        response = requests.post(
            settings.tracking_url,
            headers=make_auth_headers(settings),
            json=payload,
            timeout=60,
        )
        body = safe_response_json(response)
    except Exception:
        log.status = "Failed"
        log.error_message = frappe.get_traceback()
        log.save(ignore_permissions=True)
        raise

    log.http_status = response.status_code
    log.response_json = safe_json(body)
    if response.status_code not in (200, 201, 202):
        log.status = "Failed"
        log.error_message = body.get("message") if isinstance(body, dict) else response.text
        log.save(ignore_permissions=True)
        frappe.throw("Shipkia tracking sync failed. Check Shipment Tracking Sync Log.")

    if not tracking_result(body):
        log.status = "Failed"
        log.error_message = "Tracking response did not contain result payload."
        log.save(ignore_permissions=True)
        frappe.throw("Shipkia tracking response was missing result data. Check Sync Log.")

    apply_tracking_response(shipment, body)
    log.status = "Success"
    log.save(ignore_permissions=True)

    return {
        "success": True,
        "shipment": shipment.name,
        "status": shipment.shipkia_status,
        "message": "Shipment tracking updated.",
    }


def create_or_update_shipment_from_order_response(si, encounter, order_id: str, body: dict):
    shipment_name = frappe.db.get_value("Shipment Tracking Shipment", {"sales_invoice": si.name}, "name")
    if shipment_name:
        shipment = frappe.get_doc("Shipment Tracking Shipment", shipment_name)
    else:
        shipment = frappe.get_doc({"doctype": "Shipment Tracking Shipment"})

    shipment.sales_invoice = si.name
    shipment.patient_encounter = encounter.name if encounter else None
    shipment.patient = getattr(si, "patient", None)
    shipment.customer = getattr(si, "customer", None)
    shipment.shipkia_order_id = order_id
    shipment.raw_latest_response = safe_json(body)

    if shipment.is_new():
        shipment.insert(ignore_permissions=True)
    else:
        shipment.save(ignore_permissions=True)

    mirror_summary_fields(
        shipment,
        sales_invoice=si.name,
        encounter_name=encounter.name if encounter else None,
    )
    return shipment


def apply_tracking_response(shipment, body: dict):
    result = tracking_result(body)
    order_details = result.get("order_details") or {}
    latest = latest_timeline_entry(result)

    shipment.company = result.get("company") or ""
    shipment.company_id = result.get("company_id") or ""
    shipment.shipkia_status = result.get("status") or latest.get("status") or shipment.shipkia_status
    shipment.normalized_status = normalize_tracking_status(shipment.shipkia_status)
    shipment.shipkia_status_detail = latest.get("detail") or ""
    shipment.shipkia_tracking_id = result.get("tracking_id") or ""
    shipment.shipkia_awb_number = order_details.get("awb_number") or ""
    shipment.payment_mode = order_details.get("payment_mode") or ""
    shipment.delivery_partner = order_details.get("delivery_partner") or ""
    shipment.delivery_location = order_details.get("delivery_location") or ""
    shipment.shipkia_estimated_delivery = as_datetime(result.get("estimated_delivery"))
    shipment.shipkia_delivered_on = as_datetime(result.get("delivered_on"))
    shipment.last_synced_on = frappe.utils.now_datetime()
    shipment.raw_latest_response = safe_json(body)
    shipment.save(ignore_permissions=True)

    sync_timeline(shipment, result.get("shipment_timeline") or [])
    mirror_summary_fields(shipment, sales_invoice=shipment.sales_invoice, encounter_name=shipment.patient_encounter)


def sync_timeline(shipment, timeline_rows: list[dict]):
    existing = {
        dedupe_event_key({
            "date_time": row.date_time,
            "status": row.status,
            "detail": row.detail,
            "location": row.location,
        })
        for row in shipment.events or []
    }

    changed = False
    for row in timeline_rows:
        key = dedupe_event_key(row)
        if key in existing:
            continue
        shipment.append(
            "events",
            {
                "date_time": row.get("date_time"),
                "status": row.get("status"),
                "detail": row.get("detail"),
                "location": row.get("location"),
            },
        )
        changed = True

    if changed:
        shipment.save(ignore_permissions=True)


def mirror_summary_fields(shipment, sales_invoice: str | None, encounter_name: str | None):
    values = {
        "shipkia_order_id": shipment.shipkia_order_id,
        "shipkia_awb_number": shipment.shipkia_awb_number,
        "shipkia_status": shipment.shipkia_status,
        "shipkia_estimated_delivery": shipment.shipkia_estimated_delivery,
        "shipkia_delivered_on": shipment.shipkia_delivered_on,
        "shipkia_shipment": shipment.name,
    }
    update_doc_if_exists("Sales Invoice", sales_invoice, values)
    update_doc_if_exists("Patient Encounter", encounter_name, values)


def get_linked_encounter(si):
    for fieldname in ("source_encounter", "patient_encounter", "sr_patient_encounter", "reference_name"):
        value = getattr(si, fieldname, None)
        if value and frappe.db.exists("Patient Encounter", value):
            return frappe.get_doc("Patient Encounter", value)

    remarks = getattr(si, "remarks", "") or ""
    marker = "Patient Encounter:"
    if marker in remarks:
        candidate = remarks.split(marker, 1)[1].strip().split()[0].strip()
        if candidate and frappe.db.exists("Patient Encounter", candidate):
            return frappe.get_doc("Patient Encounter", candidate)

    encounter_name = frappe.db.get_value(
        "Patient Encounter",
        {"patient": getattr(si, "patient", None), "docstatus": 1},
        "name",
        order_by="modified desc",
    )
    if encounter_name:
        return frappe.get_doc("Patient Encounter", encounter_name)
    return None


def sync_active_shipments():
    names = frappe.get_all(
        "Shipment Tracking Shipment",
        filters={"shipkia_status": ["not in", list(TERMINAL_STATUSES)]},
        pluck="name",
        limit=ACTIVE_SYNC_DEFAULT_LIMIT,
    )
    for name in names:
        try:
            sync_tracking_for_shipment(name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Shipment Tracking auto-sync failed for {name}")
