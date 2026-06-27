from __future__ import annotations

import json
import hashlib
import time
from html import escape
from typing import Any
from urllib.parse import urlsplit

import frappe
import requests
from frappe.utils import cint, cstr
from frappe.utils.data import add_to_date, get_datetime, now_datetime

from .utils import (
    get_settings,
    make_auth_headers,
    safe_json,
    safe_response_json,
    update_doc_if_exists,
    validate_webhook_secret,
)


REATTEMPT_ISSUE_TYPE = "Request for Reattempt Delivery"
HUB_ADDRESS_ISSUE_TYPE = "Request for self collect/drop"
SUPPORT_RATE_LIMIT = 25
SUPPORT_RATE_WINDOW_SECONDS = 60
HUB_ADDRESS_COOLDOWN_HOURS = 12


def is_support_ticket_enabled() -> bool:
    settings = get_settings()
    return bool(cint(getattr(settings, "enabled", 0)) and cint(getattr(settings, "enable_support_ticket", 0)))


def assert_support_ticket_enabled():
    if not is_support_ticket_enabled():
        frappe.throw("Support Ticket is disabled in Shipment Tracking Settings.")


@frappe.whitelist()
def get_support_ticket_ui_settings():
    return {
        "enable_support_ticket": is_support_ticket_enabled(),
    }


def get_support_ticket_permission_query(user: str | None = None) -> str:
    user = user or frappe.session.user
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return ""
    return f"`tabShipment Tracking Support Ticket`.`owner` = {frappe.db.escape(user)}"


def has_support_ticket_permission(doc, ptype: str | None = None, user: str | None = None) -> bool:
    user = user or frappe.session.user
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return True
    return doc.owner == user


@frappe.whitelist()
def request_reattempt_for_invoice(invoice_name: str, message: str | None = None):
    assert_support_ticket_enabled()
    shipment = get_reference_for_invoice(invoice_name)
    default_message = "Please reattempt delivery for this shipment."
    return create_support_ticket(shipment, REATTEMPT_ISSUE_TYPE, message or default_message)


@frappe.whitelist()
def request_hub_address_for_invoice(invoice_name: str, message: str | None = None):
    assert_support_ticket_enabled()
    shipment = get_reference_for_invoice(invoice_name)
    assert_hub_address_allowed(get_reference_order_id(shipment))
    default_message = "Kindly provide hub address for self pickup."
    return create_support_ticket(shipment, HUB_ADDRESS_ISSUE_TYPE, message or default_message)


@frappe.whitelist()
def request_reattempt_for_encounter(encounter_name: str, message: str | None = None):
    assert_support_ticket_enabled()
    encounter = frappe.get_doc("Patient Encounter", encounter_name)
    validate_read_permission(encounter)
    validate_encounter_shipment_enabled(encounter)
    shipment = get_reference_for_encounter(encounter_name)
    default_message = "Please reattempt delivery for this shipment."
    return create_support_ticket(shipment, REATTEMPT_ISSUE_TYPE, message or default_message)


@frappe.whitelist()
def request_hub_address_for_encounter(encounter_name: str, message: str | None = None):
    assert_support_ticket_enabled()
    encounter = frappe.get_doc("Patient Encounter", encounter_name)
    validate_read_permission(encounter)
    validate_encounter_shipment_enabled(encounter)
    shipment = get_reference_for_encounter(encounter_name)
    assert_hub_address_allowed(get_reference_order_id(shipment))
    default_message = "Kindly provide hub address for self pickup."
    return create_support_ticket(shipment, HUB_ADDRESS_ISSUE_TYPE, message or default_message)


@frappe.whitelist()
def get_support_state_for_invoice(invoice_name: str):
    assert_support_ticket_enabled()
    reference = get_reference_for_invoice(invoice_name)
    return get_support_state(reference)


@frappe.whitelist()
def get_existing_support_state_for_invoice(invoice_name: str):
    invoice = frappe.get_doc("Sales Invoice", invoice_name)
    validate_read_permission(invoice)
    return get_existing_support_state(invoice, getattr(invoice, "si_latest_support_ticket", None))


@frappe.whitelist()
def get_support_state_for_encounter(encounter_name: str):
    assert_support_ticket_enabled()
    encounter = frappe.get_doc("Patient Encounter", encounter_name)
    validate_read_permission(encounter)
    validate_encounter_shipment_enabled(encounter)
    reference = get_reference_for_encounter(encounter_name)
    return get_support_state(reference)


@frappe.whitelist()
def get_existing_support_state_for_encounter(encounter_name: str):
    encounter = frappe.get_doc("Patient Encounter", encounter_name)
    validate_read_permission(encounter)
    return get_existing_support_state(encounter, getattr(encounter, "pe_latest_support_ticket", None))


@frappe.whitelist()
def refresh_support_ticket(ticket_name: str):
    assert_support_ticket_enabled()
    ticket = frappe.get_doc("Shipment Tracking Support Ticket", ticket_name)
    validate_read_permission(ticket)

    if not ticket.ticket_id:
        frappe.throw("Support ticket has no Shipkia Ticket ID.")

    settings = get_enabled_settings()
    url = support_url(settings, "support_get_url", "shipbu.api.admin.support.get_support_ticket")

    throttle_support_api()
    payload = {"ticket_id": ticket.ticket_id}
    log = make_support_log("Get Support Ticket", ticket, payload)

    try:
        response = requests.get(
            url,
            headers=make_auth_headers(settings),
            params=payload,
            timeout=60,
        )
        body = safe_response_json(response)
    except Exception:
        fail_log(log, frappe.get_traceback())
        raise

    log.http_status = response.status_code
    log.response_json = safe_json(body)

    if response.status_code not in (200, 201, 202):
        fail_log(log, safe_json(body))
        frappe.throw(f"Shipkia support ticket refresh failed: {support_error(body)}")

    apply_support_response(ticket, body)
    log.status = "Success"
    log.save(ignore_permissions=True)

    return support_return_payload(ticket, body, "Support ticket refreshed.")


@frappe.whitelist(allow_guest=True)
def support_ticket_update(payload: Any | None = None):
    settings = get_settings()
    assert_support_ticket_enabled()
    validate_webhook_secret(settings)
    raw_payload = payload if payload is not None else (frappe.request.get_json() or {})
    data = extract_support_payload(raw_payload)
    if not data:
        frappe.throw("Support ticket update payload is empty.")

    webhook_hash = support_update_hash(data)
    ticket = find_support_ticket_for_update(data)
    if ticket and getattr(ticket, "last_webhook_hash", "") == webhook_hash:
        update_webhook_state(ticket, data, webhook_hash, bool(ticket.shipment or ticket.sales_invoice or ticket.patient_encounter), duplicate=True)
        ticket.save(ignore_permissions=True)
        frappe.db.commit()
        return {
            **support_webhook_return_payload(ticket, "Duplicate support ticket update ignored."),
            "duplicate": True,
            "linked": bool(ticket.shipment or ticket.sales_invoice or ticket.patient_encounter),
        }

    was_new = not ticket
    ticket = upsert_ticket_from_support_update(data, raw_payload, ticket=ticket, webhook_hash=webhook_hash)
    log_support_ticket_update(ticket, raw_payload, data, was_new)
    frappe.db.commit()

    return {
        **support_webhook_return_payload(ticket, "Support ticket updated."),
        "duplicate": False,
        "linked": bool(ticket.shipment or ticket.sales_invoice or ticket.patient_encounter),
    }


def create_support_ticket(reference, issue_type: str, message: str):
    assert_support_ticket_enabled()
    validate_read_permission(reference)

    order_id = get_reference_order_id(reference)
    if not order_id:
        frappe.throw("Shipment has no Shipkia Order ID.")
    if issue_type == HUB_ADDRESS_ISSUE_TYPE:
        assert_hub_address_allowed(order_id)

    settings = get_enabled_settings()
    url = support_url(settings, "support_create_url", "shipbu.api.admin.support.create_support_ticket")
    payload = {
        "issue_type": issue_type,
        "record_type": "Order",
        "record_id": order_id,
        "message": cstr(message).strip(),
    }

    throttle_support_api()
    log = make_support_log("Create Support Ticket", reference, payload)

    try:
        response = requests.post(
            url,
            headers=make_auth_headers(settings),
            json=payload,
            timeout=60,
        )
        body = safe_response_json(response)
    except Exception:
        fail_log(log, frappe.get_traceback())
        raise

    log.http_status = response.status_code
    log.response_json = safe_json(body)

    if response.status_code not in (200, 201, 202):
        fail_log(log, safe_json(body))
        frappe.throw(f"Shipkia support ticket failed: {support_error(body)}")

    data = support_data(body)
    if not data.get("id"):
        fail_log(log, "Missing ticket id in Shipkia support response.")
        frappe.throw(f"Shipkia support ticket failed: {safe_json(body)}")

    ticket = upsert_local_ticket(reference, issue_type, message, body)
    add_support_response_comment(reference, ticket, "created")
    log.status = "Success"
    log.reference_doctype = "Shipment Tracking Support Ticket"
    log.reference_name = ticket.name
    log.shipkia_order_id = order_id
    log.save(ignore_permissions=True)
    frappe.db.commit()

    return support_return_payload(ticket, body, "Support ticket created.")


def get_enabled_settings():
    assert_support_ticket_enabled()
    settings = get_settings()
    if not settings.enabled:
        frappe.throw("Shipment Tracking is disabled in settings.")
    return settings


def support_url(settings, fieldname: str, method_path: str) -> str:
    configured = cstr(getattr(settings, fieldname, "")).strip()
    if configured:
        return configured

    for base_field in ("tracking_url", "create_order_url"):
        candidate = cstr(getattr(settings, base_field, "")).strip()
        if "/api/method/" in candidate:
            base = candidate.split("/api/method/", 1)[0]
            return f"{base}/api/method/{method_path}"
        if candidate:
            parts = urlsplit(candidate)
            if parts.scheme and parts.netloc:
                return f"{parts.scheme}://{parts.netloc}/api/method/{method_path}"

    frappe.throw(f"Configure {fieldname.replace('_', ' ').title()} in Shipment Tracking Settings.")


def throttle_support_api():
    key = "shipment_tracking:support_api_rate"
    now = time.time()
    cache = frappe.cache()
    raw = cache.get_value(key)

    try:
        calls = json.loads(raw) if isinstance(raw, str) else list(raw or [])
    except Exception:
        calls = []

    calls = [float(ts) for ts in calls if now - float(ts) < SUPPORT_RATE_WINDOW_SECONDS]
    if len(calls) >= SUPPORT_RATE_LIMIT:
        frappe.throw("Shipkia support API rate limit reached. Please try again after a minute.")

    calls.append(now)
    cache.set_value(key, json.dumps(calls), expires_in_sec=SUPPORT_RATE_WINDOW_SECONDS)


def get_reference_for_invoice(invoice_name: str):
    invoice = frappe.get_doc("Sales Invoice", invoice_name)
    validate_read_permission(invoice)

    shipment_name = (
        getattr(invoice, "si_shipkia_shipment", None)
        or frappe.db.get_value("Shipment Tracking Shipment", {"sales_invoice": invoice_name}, "name")
    )
    if not shipment_name:
        if getattr(invoice, "si_shipkia_order_id", None):
            return invoice
        frappe.throw("No shipment record linked to this Sales Invoice.")
    return frappe.get_doc("Shipment Tracking Shipment", shipment_name)


def get_reference_for_encounter(encounter_name: str):
    encounter = frappe.get_doc("Patient Encounter", encounter_name)
    validate_read_permission(encounter)

    shipment_name = (
        getattr(encounter, "pe_shipkia_shipment", None)
        or frappe.db.get_value("Shipment Tracking Shipment", {"patient_encounter": encounter_name}, "name")
    )
    if not shipment_name:
        if getattr(encounter, "pe_shipkia_order_id", None):
            return encounter
        frappe.throw("No shipment record linked to this Patient Encounter.")
    return frappe.get_doc("Shipment Tracking Shipment", shipment_name)


def get_reference_order_id(reference) -> str:
    return cstr(
        getattr(reference, "shipkia_order_id", None)
        or getattr(reference, "si_shipkia_order_id", None)
        or getattr(reference, "pe_shipkia_order_id", None)
    ).strip()


def get_support_state(reference) -> dict[str, Any]:
    order_id = get_reference_order_id(reference)
    latest_ticket = latest_visible_ticket(order_id)
    cooldown = get_hub_address_cooldown(order_id)

    return {
        "success": True,
        "order_id": order_id,
        "latest_ticket": latest_ticket.name if latest_ticket else "",
        "latest_ticket_id": latest_ticket.ticket_id if latest_ticket else "",
        "latest_issue_type": latest_ticket.issue_type if latest_ticket else "",
        "latest_stage": latest_ticket.stage if latest_ticket else "",
        "latest_response": latest_ticket.latest_response if latest_ticket else "",
        "responses": support_response_entries(latest_ticket) if latest_ticket else [],
        "latest_requested_on": latest_ticket.creation if latest_ticket else None,
        "hub_address_disabled": bool(cooldown),
        "hub_address_disabled_until": cooldown.get("disabled_until") if cooldown else None,
        "hub_address_disabled_message": cooldown.get("message") if cooldown else "",
    }


def get_existing_support_state(reference, latest_ticket_name: str | None = None) -> dict[str, Any]:
    order_id = get_reference_order_id(reference)
    latest_ticket = existing_visible_ticket(order_id, latest_ticket_name)

    return {
        "success": True,
        "read_only": True,
        "has_existing_ticket": bool(latest_ticket),
        "order_id": order_id,
        "latest_ticket": latest_ticket.name if latest_ticket else "",
        "latest_ticket_id": latest_ticket.ticket_id if latest_ticket else "",
        "latest_issue_type": latest_ticket.issue_type if latest_ticket else "",
        "latest_stage": latest_ticket.stage if latest_ticket else "",
        "latest_response": latest_ticket.latest_response if latest_ticket else "",
        "responses": support_response_entries(latest_ticket) if latest_ticket else [],
        "latest_requested_on": latest_ticket.creation if latest_ticket else None,
    }


def existing_visible_ticket(order_id: str, latest_ticket_name: str | None = None):
    if latest_ticket_name and frappe.db.exists("Shipment Tracking Support Ticket", latest_ticket_name):
        ticket = frappe.get_doc("Shipment Tracking Support Ticket", latest_ticket_name)
        validate_read_permission(ticket)
        return ticket

    return latest_visible_ticket(order_id)


def latest_visible_ticket(order_id: str):
    if not order_id:
        return None

    filters = {"shipkia_order_id": order_id}
    if "System Manager" not in frappe.get_roles() and frappe.session.user != "Administrator":
        filters["owner"] = frappe.session.user

    name = frappe.db.get_value(
        "Shipment Tracking Support Ticket",
        filters,
        "name",
        order_by="creation desc",
    )
    return frappe.get_doc("Shipment Tracking Support Ticket", name) if name else None


def assert_hub_address_allowed(order_id: str):
    cooldown = get_hub_address_cooldown(order_id)
    if cooldown:
        frappe.throw(cooldown["message"])


def get_hub_address_cooldown(order_id: str) -> dict[str, Any] | None:
    if not order_id:
        return None

    cutoff = add_to_date(now_datetime(), hours=-HUB_ADDRESS_COOLDOWN_HOURS)
    row = frappe.db.get_value(
        "Shipment Tracking Support Ticket",
        {
            "shipkia_order_id": order_id,
            "issue_type": REATTEMPT_ISSUE_TYPE,
            "creation": [">=", cutoff],
        },
        ["name", "ticket_id", "creation"],
        order_by="creation desc",
        as_dict=True,
    )
    if not row:
        return None

    disabled_until = add_to_date(get_datetime(row.creation), hours=HUB_ADDRESS_COOLDOWN_HOURS)
    return {
        "ticket": row.name,
        "ticket_id": row.ticket_id,
        "disabled_until": disabled_until,
        "message": (
            "Hub address request is disabled for 12 hours after a reattempt request. "
            f"Try again after {disabled_until}."
        ),
    }


def validate_read_permission(doc):
    if not frappe.has_permission(doc.doctype, "read", doc=doc):
        frappe.throw("Not permitted.", frappe.PermissionError)


def validate_encounter_shipment_enabled(encounter):
    if getattr(encounter, "pe_shipkia_order_id", None) or getattr(encounter, "pe_shipkia_shipment", None):
        return

    for fieldname in ("has_shipment_tracking", "pe_has_shipment_tracking", "shipment_tracking"):
        if encounter.meta.has_field(fieldname) and getattr(encounter, fieldname, None):
            return

    encounter_type = getattr(encounter, "encounter_type", None)
    if (
        encounter_type
        and frappe.db.exists("DocType", "Encounter Type")
        and frappe.db.exists("Encounter Type", encounter_type)
    ):
        et = frappe.get_doc("Encounter Type", encounter_type)
        for fieldname in ("has_shipment_tracking", "shipment_tracking"):
            if et.meta.has_field(fieldname) and getattr(et, fieldname, None):
                return

    if getattr(encounter, "sr_encounter_place", None) == "Online":
        return

    frappe.throw("Shipment tracking is not enabled for this Patient Encounter.")


def support_data(body: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(body, dict):
        return extract_support_payload(body)

    direct_keys = {
        "comments",
        "ticket_id",
        "partner_ticket_id",
        "stage",
        "issue_type",
        "record_id",
        "awb",
    }
    if any(key in body for key in direct_keys):
        return body

    extracted = extract_support_payload(body)
    if extracted is not body and extracted:
        return extracted

    message = body.get("message") if isinstance(body, dict) else {}
    if isinstance(message, dict):
        data = message.get("data")
        if isinstance(data, dict):
            return data
    return {}


def extract_support_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list):
        payload = payload[0] if payload else {}

    if isinstance(payload, dict) and isinstance(payload.get("body"), dict):
        return payload.get("body") or {}

    return payload if isinstance(payload, dict) else {}


def support_error(body: dict[str, Any]) -> str:
    message = body.get("message") if isinstance(body, dict) else None
    if isinstance(message, dict):
        return cstr(message.get("error") or message)
    return safe_json(body)


def upsert_local_ticket(reference, issue_type: str, message: str, body: dict[str, Any]):
    data = support_data(body)
    ticket_id = data.get("id")
    ticket_name = frappe.db.get_value("Shipment Tracking Support Ticket", {"ticket_id": ticket_id}, "name")

    if ticket_name:
        ticket = frappe.get_doc("Shipment Tracking Support Ticket", ticket_name)
        validate_read_permission(ticket)
    else:
        ticket = frappe.get_doc({"doctype": "Shipment Tracking Support Ticket"})
        ticket.owner = frappe.session.user

    ticket.ticket_id = ticket_id
    if ticket.meta.has_field("partner_ticket_id"):
        ticket.partner_ticket_id = data.get("partner_ticket_id") or ticket.partner_ticket_id
    ticket.issue_type = data.get("issue_type") or issue_type
    ticket.stage = data.get("stage") or ""
    ticket.shipment = reference.name if reference.doctype == "Shipment Tracking Shipment" else None
    ticket.sales_invoice = get_reference_sales_invoice(reference)
    ticket.patient_encounter = get_reference_patient_encounter(reference)
    ticket.shipkia_order_id = data.get("record_id") or get_reference_order_id(reference)
    ticket.awb_number = data.get("awb_number") or getattr(reference, "shipkia_awb_number", None) or getattr(reference, "si_shipkia_awb_number", None) or getattr(reference, "pe_shipkia_awb_number", None)
    ticket.courier_partner = data.get("courier_partner") or getattr(reference, "delivery_partner", None) or getattr(reference, "si_delivery_partner", None) or getattr(reference, "pe_delivery_partner", None)
    ticket.message = data.get("message") or message
    ticket.latest_response = latest_response_text(data)
    ticket.raw_latest_response = safe_json(body)

    if ticket.is_new():
        ticket.insert(ignore_permissions=True)
    else:
        ticket.save(ignore_permissions=True)

    mirror_support_fields(ticket)
    return ticket


def upsert_ticket_from_support_update(data: dict[str, Any], raw_payload: Any, ticket=None, webhook_hash: str | None = None):
    ticket = ticket or find_support_ticket_for_update(data)
    if not ticket:
        ticket = frappe.get_doc({"doctype": "Shipment Tracking Support Ticket"})

    reference = get_reference_for_support_update(data)
    ticket.ticket_id = cstr(data.get("ticket_id") or data.get("id") or ticket.ticket_id).strip()
    if ticket.meta.has_field("partner_ticket_id"):
        ticket.partner_ticket_id = cstr(data.get("partner_ticket_id") or ticket.partner_ticket_id).strip()
    ticket.issue_type = cstr(data.get("issue_type") or ticket.issue_type).strip()
    ticket.stage = cstr(data.get("stage") or ticket.stage).strip()
    ticket.shipkia_order_id = cstr(data.get("record_id") or ticket.shipkia_order_id or get_reference_order_id(reference)).strip()
    ticket.awb_number = cstr(data.get("awb") or data.get("awb_number") or ticket.awb_number).strip()
    ticket.courier_partner = cstr(data.get("courier_partner") or ticket.courier_partner).strip()
    ticket.message = cstr(data.get("description") or data.get("message") or ticket.message).strip()

    if reference:
        ticket.shipment = reference.name if reference.doctype == "Shipment Tracking Shipment" else ticket.shipment
        ticket.sales_invoice = get_reference_sales_invoice(reference) or ticket.sales_invoice
        ticket.patient_encounter = get_reference_patient_encounter(reference) or ticket.patient_encounter
        if ticket.is_new() and getattr(reference, "owner", None):
            ticket.owner = reference.owner
    elif ticket.is_new():
        ticket.owner = "Administrator"

    fill_missing_support_links(ticket)
    linked = bool(ticket.shipment or ticket.sales_invoice or ticket.patient_encounter)
    update_webhook_state(ticket, data, webhook_hash or support_update_hash(data), linked)
    ticket.latest_response = latest_response_text(data)
    ticket.raw_latest_response = safe_json(raw_payload)

    if ticket.is_new():
        ticket.insert(ignore_permissions=True)
    else:
        ticket.save(ignore_permissions=True)

    mirror_support_fields(ticket)
    return ticket


def update_webhook_state(ticket, data: dict[str, Any], webhook_hash: str, linked: bool, duplicate: bool = False):
    if ticket.meta.has_field("last_webhook_received_on"):
        ticket.last_webhook_received_on = now_datetime()
    if ticket.meta.has_field("webhook_update_count"):
        ticket.webhook_update_count = (ticket.webhook_update_count or 0) + 1
    if ticket.meta.has_field("last_webhook_comment_on"):
        comment_on = latest_comment_created_on(data)
        ticket.last_webhook_comment_on = parse_webhook_datetime(comment_on) or ticket.last_webhook_comment_on
    if ticket.meta.has_field("last_webhook_hash") and not duplicate:
        ticket.last_webhook_hash = webhook_hash
    if ticket.meta.has_field("is_unlinked"):
        ticket.is_unlinked = 0 if linked else 1
    if ticket.meta.has_field("linking_status"):
        if linked:
            ticket.linking_status = "Linked to shipment, sales invoice, or patient encounter."
        else:
            ticket.linking_status = (
                "No matching Shipment Tracking Shipment, Sales Invoice, or Patient Encounter found "
                f"for Order ID {cstr(data.get('record_id')).strip() or '-'} / AWB {cstr(data.get('awb') or data.get('awb_number')).strip() or '-'}."
            )


def latest_comment_created_on(data: dict[str, Any]) -> str:
    comments = data.get("comments") or []
    if comments and isinstance(comments, list):
        comment = comments[-1] or {}
        return cstr(comment.get("created_on") or comment.get("creation") or "").strip()
    return ""


def parse_webhook_datetime(value: str):
    value = cstr(value).strip()
    if not value:
        return None

    parsed = get_datetime(value)
    if getattr(parsed, "tzinfo", None):
        parsed = parsed.replace(tzinfo=None)
    return parsed


def support_update_hash(data: dict[str, Any]) -> str:
    latest_comment = {}
    comments = data.get("comments") or []
    if comments and isinstance(comments, list) and isinstance(comments[-1], dict):
        latest_comment = comments[-1]

    key = {
        "ticket_id": cstr(data.get("ticket_id") or data.get("id")).strip(),
        "partner_ticket_id": cstr(data.get("partner_ticket_id")).strip(),
        "stage": cstr(data.get("stage")).strip(),
        "awb": cstr(data.get("awb") or data.get("awb_number")).strip(),
        "record_id": cstr(data.get("record_id")).strip(),
        "latest_comment": cstr(latest_comment.get("comment") or latest_comment.get("message")).strip(),
        "latest_comment_created_on": cstr(latest_comment.get("created_on") or latest_comment.get("creation")).strip(),
    }
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()


def find_support_ticket_for_update(data: dict[str, Any]):
    for fieldname, value in (
        ("ticket_id", data.get("ticket_id") or data.get("id")),
        ("partner_ticket_id", data.get("partner_ticket_id")),
    ):
        value = cstr(value).strip()
        if not value:
            continue
        if fieldname == "partner_ticket_id" and not frappe.get_meta("Shipment Tracking Support Ticket").has_field(fieldname):
            continue
        name = frappe.db.get_value("Shipment Tracking Support Ticket", {fieldname: value}, "name")
        if name:
            return frappe.get_doc("Shipment Tracking Support Ticket", name)

    order_id = cstr(data.get("record_id")).strip()
    awb = cstr(data.get("awb") or data.get("awb_number")).strip()
    for filters in (
        {"shipkia_order_id": order_id} if order_id else None,
        {"awb_number": awb} if awb else None,
    ):
        if not filters:
            continue
        name = frappe.db.get_value(
            "Shipment Tracking Support Ticket",
            filters,
            "name",
            order_by="modified desc",
        )
        if name:
            return frappe.get_doc("Shipment Tracking Support Ticket", name)

    return None


def get_reference_for_support_update(data: dict[str, Any]):
    order_id = cstr(data.get("record_id")).strip()
    awb = cstr(data.get("awb") or data.get("awb_number")).strip()

    shipment_name = None
    if order_id:
        shipment_name = frappe.db.get_value("Shipment Tracking Shipment", {"shipkia_order_id": order_id}, "name")
    if not shipment_name and awb:
        shipment_name = frappe.db.get_value("Shipment Tracking Shipment", {"shipkia_awb_number": awb}, "name")
    if shipment_name:
        return frappe.get_doc("Shipment Tracking Shipment", shipment_name)

    invoice_name = None
    if order_id:
        invoice_name = frappe.db.get_value("Sales Invoice", {"si_shipkia_order_id": order_id}, "name")
    if not invoice_name and awb:
        invoice_name = frappe.db.get_value("Sales Invoice", {"si_shipkia_awb_number": awb}, "name")
    if invoice_name:
        return frappe.get_doc("Sales Invoice", invoice_name)

    encounter_name = None
    if order_id:
        encounter_name = frappe.db.get_value("Patient Encounter", {"pe_shipkia_order_id": order_id}, "name")
    if not encounter_name and awb:
        encounter_name = frappe.db.get_value("Patient Encounter", {"pe_shipkia_awb_number": awb}, "name")
    if encounter_name:
        return frappe.get_doc("Patient Encounter", encounter_name)

    return None


def fill_missing_support_links(ticket):
    if ticket.shipment:
        shipment = frappe.get_doc("Shipment Tracking Shipment", ticket.shipment)
        ticket.sales_invoice = ticket.sales_invoice or shipment.sales_invoice
        ticket.patient_encounter = ticket.patient_encounter or shipment.patient_encounter
        return

    if ticket.sales_invoice and frappe.db.exists("Sales Invoice", ticket.sales_invoice):
        shipment_name = frappe.db.get_value("Shipment Tracking Shipment", {"sales_invoice": ticket.sales_invoice}, "name")
        if shipment_name:
            ticket.shipment = shipment_name
            shipment = frappe.get_doc("Shipment Tracking Shipment", shipment_name)
            ticket.patient_encounter = ticket.patient_encounter or shipment.patient_encounter
            return

    if ticket.patient_encounter and frappe.db.exists("Patient Encounter", ticket.patient_encounter):
        shipment_name = frappe.db.get_value("Shipment Tracking Shipment", {"patient_encounter": ticket.patient_encounter}, "name")
        if shipment_name:
            ticket.shipment = shipment_name
            shipment = frappe.get_doc("Shipment Tracking Shipment", shipment_name)
            ticket.sales_invoice = ticket.sales_invoice or shipment.sales_invoice


def get_reference_sales_invoice(reference) -> str | None:
    if reference.doctype == "Shipment Tracking Shipment":
        return reference.sales_invoice
    if reference.doctype == "Sales Invoice":
        return reference.name
    return None


def get_reference_patient_encounter(reference) -> str | None:
    if reference.doctype == "Shipment Tracking Shipment":
        return reference.patient_encounter
    if reference.doctype == "Patient Encounter":
        return reference.name
    return None


def apply_support_response(ticket, body: dict[str, Any]):
    data = support_data(body)
    ticket.issue_type = data.get("issue_type") or ticket.issue_type
    ticket.stage = data.get("stage") or ticket.stage
    ticket.awb_number = data.get("awb_number") or ticket.awb_number
    ticket.courier_partner = data.get("courier_partner") or ticket.courier_partner
    ticket.message = data.get("message") or ticket.message
    ticket.latest_response = latest_response_text(data)
    ticket.raw_latest_response = safe_json(body)
    ticket.save(ignore_permissions=True)
    mirror_support_fields(ticket)
    add_support_response_comment(ticket, ticket, "refreshed")


def latest_response_text(data: dict[str, Any]) -> str:
    comments = data.get("comments") or []
    if comments and isinstance(comments, list):
        comment = comments[-1] or {}
        return cstr(comment.get("comment") or comment.get("message") or "")
    return cstr(data.get("message") or data.get("description") or "")


def support_response_entries(ticket) -> list[dict[str, Any]]:
    if not ticket:
        return []

    data = {}
    try:
        raw = json.loads(ticket.raw_latest_response or "{}")
        data = support_data(raw)
    except Exception:
        data = {}

    entries = []
    comments = data.get("comments") or []
    if isinstance(comments, list):
        for row in comments:
            if not isinstance(row, dict):
                continue
            text = cstr(row.get("comment") or row.get("message") or "").strip()
            if not text:
                continue
            entries.append(
                {
                    "text": text,
                    "type": row.get("type") or "",
                    "by": row.get("comment_by") or "",
                    "created_on": row.get("created_on") or row.get("creation") or "",
                    "attachment": row.get("attachment"),
                }
            )

    initial = cstr(data.get("message") or data.get("description") or ticket.message or "").strip()
    if initial and not any(row.get("text") == initial for row in entries):
        entries.append(
            {
                "text": initial,
                "type": "Initial",
                "by": "",
                "created_on": data.get("creation") or ticket.creation,
            }
        )

    if not entries and ticket.latest_response:
        entries.append(
            {
                "text": ticket.latest_response,
                "type": "",
                "by": "",
                "created_on": ticket.modified,
            }
        )

    return entries


def mirror_support_fields(ticket):
    values = {
        "latest_support_ticket": ticket.name,
        "latest_support_ticket_id": ticket.ticket_id,
        "latest_support_issue_type": ticket.issue_type,
        "latest_support_stage": ticket.stage,
        "latest_support_response": ticket.latest_response,
        "latest_support_requested_on": ticket.creation,
    }
    update_doc_if_exists("Shipment Tracking Shipment", ticket.shipment, values)

    si_values = {
        f"si_{key}": value
        for key, value in values.items()
        if key != "latest_support_ticket"
    }
    si_values["si_latest_support_ticket"] = ticket.name
    update_doc_if_exists("Sales Invoice", ticket.sales_invoice, si_values)

    pe_values = {
        f"pe_{key}": value
        for key, value in values.items()
        if key != "latest_support_ticket"
    }
    pe_values["pe_latest_support_ticket"] = ticket.name
    update_doc_if_exists("Patient Encounter", ticket.patient_encounter, pe_values)


def add_support_response_comment(reference, ticket, action: str):
    lines = [
        f"Shipkia support ticket {action}: {escape(ticket.ticket_id or ticket.name)}",
        f"Issue Type: {escape(ticket.issue_type or '')}",
        f"Stage: {escape(ticket.stage or '')}",
        f"AWB: {escape(ticket.awb_number or '')}",
        f"Courier: {escape(ticket.courier_partner or '')}",
        "Latest response updated on the support ticket.",
    ]
    linking_status = cstr(getattr(ticket, "linking_status", "")).strip()
    if action == "updated" and linking_status:
        lines.append(f"Linking Status: {escape(linking_status)}")

    message = "<br>".join(lines)

    targets = []
    if reference.doctype in ("Sales Invoice", "Patient Encounter", "Shipment Tracking Shipment"):
        targets.append((reference.doctype, reference.name))
    for doctype, name in (
        ("Sales Invoice", ticket.sales_invoice),
        ("Patient Encounter", ticket.patient_encounter),
        ("Shipment Tracking Shipment", ticket.shipment),
        ("Shipment Tracking Support Ticket", ticket.name),
    ):
        if name:
            targets.append((doctype, name))

    seen = set()
    for doctype, name in targets:
        key = (doctype, name)
        if key in seen or not frappe.db.exists(doctype, name):
            continue
        seen.add(key)
        try:
            doc = frappe.get_doc(doctype, name)
            doc.add_comment("Comment", message)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"Shipment support comment failed for {doctype} {name}",
            )


def support_return_payload(ticket, body: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "success": True,
        "message": message,
        "ticket": ticket.name,
        "ticket_id": ticket.ticket_id,
        "partner_ticket_id": getattr(ticket, "partner_ticket_id", ""),
        "stage": ticket.stage,
        "awb_number": ticket.awb_number,
        "courier_partner": ticket.courier_partner,
        "latest_response": ticket.latest_response,
        "responses": support_response_entries(ticket),
        "latest_requested_on": ticket.creation,
        "raw_response": body,
    }


def support_webhook_return_payload(ticket, message: str) -> dict[str, Any]:
    return {
        "success": True,
        "message": message,
        "ticket": ticket.name,
        "ticket_id": ticket.ticket_id,
        "partner_ticket_id": getattr(ticket, "partner_ticket_id", ""),
        "stage": ticket.stage,
        "awb_number": ticket.awb_number,
        "latest_response": ticket.latest_response,
        "linking_status": getattr(ticket, "linking_status", ""),
    }


def log_support_ticket_update(ticket, raw_payload: Any, data: dict[str, Any], was_new: bool):
    linked = bool(ticket.shipment or ticket.sales_invoice or ticket.patient_encounter)
    reason = "new" if was_new else "changed"
    if not linked:
        reason = "unlinked"

    log = frappe.get_doc(
        {
            "doctype": "Shipment Tracking Sync Log",
            "direction": "Inbound",
            "action": "Support Ticket Update",
            "reference_doctype": "Shipment Tracking Support Ticket",
            "reference_name": ticket.name,
            "shipkia_order_id": ticket.shipkia_order_id or data.get("record_id"),
            "request_json": safe_json(raw_payload),
            "response_json": safe_json(
                {
                    "reason": reason,
                    "linked": linked,
                    "ticket": ticket.name,
                    "ticket_id": ticket.ticket_id,
                    "partner_ticket_id": getattr(ticket, "partner_ticket_id", ""),
                    "awb_number": ticket.awb_number,
                    "latest_comment_created_on": latest_comment_created_on(data),
                    "linking_status": getattr(ticket, "linking_status", ""),
                }
            ),
            "status": "Success",
        }
    )
    log.insert(ignore_permissions=True)


def cleanup_successful_support_update_logs(days: int = 30):
    if not is_support_ticket_enabled():
        return

    cutoff = add_to_date(now_datetime(), days=-days)
    frappe.db.delete(
        "Shipment Tracking Sync Log",
        {
            "direction": "Inbound",
            "action": "Support Ticket Update",
            "status": "Success",
            "modified": ["<", cutoff],
        },
    )
    frappe.db.commit()


def make_support_log(action: str, reference, payload: dict[str, Any]):
    reference_doctype = getattr(reference, "doctype", "Shipment Tracking Shipment")
    reference_name = getattr(reference, "name", None)
    shipkia_order_id = get_reference_order_id(reference)

    return frappe.get_doc(
        {
            "doctype": "Shipment Tracking Sync Log",
            "direction": "Outbound",
            "action": action,
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "shipkia_order_id": shipkia_order_id,
            "request_json": safe_json(payload),
            "status": "Running",
        }
    ).insert(ignore_permissions=True)


def fail_log(log, error_message: str):
    log.status = "Failed"
    log.error_message = error_message
    log.save(ignore_permissions=True)
    frappe.db.commit()
