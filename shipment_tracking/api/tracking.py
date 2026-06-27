from __future__ import annotations

import frappe
import requests
from frappe.utils import cint

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
def get_tracking_ui_settings():
    settings = get_settings()
    return {
        "enable_manual_tracking_refresh": bool(cint(getattr(settings, "enable_manual_tracking_refresh", 0)))
    }


@frappe.whitelist()
def sync_tracking_for_shipment(shipment_name: str):
    shipment = frappe.get_doc("Shipment Tracking Shipment", shipment_name)
    if not shipment.shipkia_order_id:
        frappe.throw("Shipment has no Shipkia Order ID.")
    return sync_tracking_by_order_id(shipment.shipkia_order_id)


@frappe.whitelist()
def sync_tracking_for_invoice(invoice_name: str):
    validate_manual_tracking_refresh_enabled()
    invoice = frappe.get_doc("Sales Invoice", invoice_name)
    shipment = get_or_create_shipment(si=invoice, order_id=getattr(invoice, "si_shipkia_order_id", None), create=False)
    if not shipment:
        frappe.throw("No shipment record linked to this Sales Invoice.")
    repair_shipment_links(shipment, si=invoice, order_id=getattr(invoice, "si_shipkia_order_id", None))
    return sync_tracking_for_shipment(shipment.name)


@frappe.whitelist()
def sync_tracking_for_encounter(encounter_name: str):
    validate_manual_tracking_refresh_enabled()
    encounter = frappe.get_doc("Patient Encounter", encounter_name)
    shipment = get_or_create_shipment(
        encounter=encounter,
        order_id=getattr(encounter, "pe_shipkia_order_id", None),
        create=False,
    )
    if not shipment:
        frappe.throw("No shipment record linked to this Patient Encounter.")
    repair_shipment_links(shipment, encounter=encounter, order_id=getattr(encounter, "pe_shipkia_order_id", None))
    return sync_tracking_for_shipment(shipment.name)


def validate_manual_tracking_refresh_enabled():
    settings = get_settings()
    if not cint(getattr(settings, "enable_manual_tracking_refresh", 0)):
        frappe.throw("Manual shipment status refresh is disabled in Shipment Tracking Settings.")


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
        log.error_message = str(frappe.get_traceback())
        log.save(ignore_permissions=True)
        frappe.db.commit()
        raise

    log.http_status = response.status_code
    log.response_json = safe_json(body)
    if response.status_code not in (200, 201, 202):
        log.status = "Failed"
        log.error_message = (
            safe_json(body.get("message"))
            if isinstance(body, dict)
            else str(response.text)
        )
        log.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.throw("Shipkia tracking sync failed. Check Shipment Tracking Sync Log.")

    if not tracking_result(body):
        log.status = "Failed"
        if isinstance(body, dict) and body.get("raw_text"):
            log.error_message = (
                "Tracking URL returned non-JSON/HTML content. "
                "Please configure Shipment Tracking Settings > Tracking URL to the Shipkia API endpoint, "
                "not the public tracking web page."
            )
        else:
            log.error_message = "Tracking response did not contain result payload."
        log.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.throw(log.error_message)

    apply_tracking_response(shipment, body)
    log.status = "Success"
    log.save(ignore_permissions=True)

    return {
        "success": True,
        "shipment": shipment.name,
        "status": shipment.shipkia_status,
        "message": "Shipment tracking updated.",
    }


def get_or_create_shipment(si=None, encounter=None, order_id: str | None = None, create: bool = True):
    order_id = (order_id or "").strip()
    lookups = []
    if order_id:
        lookups.append({"shipkia_order_id": order_id})
    if si:
        lookups.extend(
            [
                {"name": getattr(si, "si_shipkia_shipment", None)},
                {"sales_invoice": si.name},
            ]
        )
    if encounter:
        lookups.extend(
            [
                {"name": getattr(encounter, "pe_shipkia_shipment", None)},
                {"patient_encounter": encounter.name},
            ]
        )

    seen = set()
    for filters in lookups:
        filters = {key: value for key, value in filters.items() if value}
        if not filters:
            continue
        key = tuple(sorted(filters.items()))
        if key in seen:
            continue
        seen.add(key)
        shipment_name = frappe.db.get_value("Shipment Tracking Shipment", filters, "name")
        if shipment_name:
            return frappe.get_doc("Shipment Tracking Shipment", shipment_name)

    if not create:
        return None
    return frappe.get_doc({"doctype": "Shipment Tracking Shipment"})


def repair_shipment_links(shipment, si=None, encounter=None, order_id: str | None = None) -> bool:
    changed = False

    if si:
        if shipment.sales_invoice and shipment.sales_invoice != si.name:
            frappe.throw(
                f"Shipment {shipment.name} is already linked to Sales Invoice {shipment.sales_invoice}."
            )
        if not shipment.sales_invoice:
            shipment.sales_invoice = si.name
            changed = True
        if getattr(si, "patient", None) and shipment.patient != si.patient:
            shipment.patient = si.patient
            changed = True
        if getattr(si, "customer", None) and shipment.customer != si.customer:
            shipment.customer = si.customer
            changed = True

    if encounter and shipment.patient_encounter and shipment.patient_encounter != encounter.name:
        frappe.throw(
            f"Shipment {shipment.name} is already linked to Patient Encounter {shipment.patient_encounter}."
        )
    if encounter and not shipment.patient_encounter:
        shipment.patient_encounter = encounter.name
        changed = True
    if encounter and getattr(encounter, "patient", None) and shipment.patient != encounter.patient:
        shipment.patient = encounter.patient
        changed = True

    if order_id and shipment.shipkia_order_id != order_id:
        shipment.shipkia_order_id = order_id
        changed = True

    if changed and not shipment.is_new():
        shipment.save(ignore_permissions=True)
        mirror_summary_fields(
            shipment,
            sales_invoice=shipment.sales_invoice,
            encounter_name=shipment.patient_encounter,
        )

    return changed


def create_or_update_shipment_from_order_response(si, encounter, order_id: str, body: dict):
    shipment = get_or_create_shipment(si=si, encounter=encounter, order_id=order_id)
    repair_shipment_links(shipment, si=si, encounter=encounter, order_id=order_id)
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
    shipment.shipkia_stage = result.get("order_stage") or order_details.get("order_stage") or shipment.shipkia_stage
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

    # Sales Invoice fields
    si_values = {
        "si_shipkia_order_id": shipment.shipkia_order_id,
        "si_shipkia_awb_number": shipment.shipkia_awb_number,
        "si_delivery_partner": shipment.delivery_partner,
        "si_shipkia_stage": shipment.shipkia_stage,
        "si_shipkia_status": shipment.shipkia_status,
        "si_shipkia_estimated_delivery": shipment.shipkia_estimated_delivery,
        "si_shipkia_delivered_on": shipment.shipkia_delivered_on,
        "si_shipkia_shipment": shipment.name,
    }

    # Patient Encounter fields
    pe_values = {
        "pe_shipkia_order_id": shipment.shipkia_order_id,
        "pe_shipkia_awb_number": shipment.shipkia_awb_number,
        "pe_delivery_partner": shipment.delivery_partner,
        "pe_shipkia_stage": shipment.shipkia_stage,
        "pe_shipkia_status": shipment.shipkia_status,
        "pe_shipkia_estimated_delivery": shipment.shipkia_estimated_delivery,
        "pe_shipkia_delivered_on": shipment.shipkia_delivered_on,
        "pe_shipkia_shipment": shipment.name,
    }

    update_doc_if_exists("Sales Invoice", sales_invoice, si_values)
    update_doc_if_exists("Patient Encounter", encounter_name, pe_values)


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
