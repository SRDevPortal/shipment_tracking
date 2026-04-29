from __future__ import annotations

import frappe
from frappe.utils import get_datetime

from .tracking import mirror_summary_fields


def extract_webhook_body(payload):
    if isinstance(payload, list):
        payload = payload[0] if payload else {}

    if isinstance(payload, dict) and isinstance(payload.get("body"), dict):
        return payload.get("body") or {}

    return payload if isinstance(payload, dict) else {}


def clean(value):
    if value is None:
        return None

    value = str(value).strip()
    return None if value.lower() in ("", "none", "null") else value


def first_clean_value(data, *fieldnames):
    for fieldname in fieldnames:
        value = clean(data.get(fieldname))
        if value:
            return value

    return None


@frappe.whitelist(allow_guest=True)
def order_status_update():
    """
    Receives webhook from n8n → updates Shipment Tracking Shipment
    """

    # -----------------------------
    # 🔐 SECURITY (WITH TOGGLE)
    # -----------------------------
    settings = frappe.get_single("Shipment Tracking Settings")

    enable_security = settings.get("enable_webhook_security")
    SECRET = settings.get_password("webhook_secret", raise_exception=False) or ""
    incoming_secret = frappe.get_request_header("X-Webhook-Secret")

    # Apply validation ONLY if enabled
    if enable_security:
        if not SECRET or incoming_secret != SECRET:
            frappe.local.response["http_status_code"] = 403
            return {
                "success": False,
                "message": "Unauthorized request"
            }

    # -----------------------------
    # REQUEST DATA
    # -----------------------------
    payload = frappe.request.get_json() or {}
    data = extract_webhook_body(payload)

    order_id = clean(data.get("order_id"))
    if not order_id:
        return {
            "success": False,
            "message": "order_id is required",
            "data": payload
        }

    # -----------------------------
    # GET / CREATE SHIPMENT
    # -----------------------------
    shipment_name = frappe.db.get_value(
        "Shipment Tracking Shipment",
        {"shipkia_order_id": order_id},
        "name"
    )

    if not shipment_name:
        shipment = frappe.get_doc({
            "doctype": "Shipment Tracking Shipment",
            "shipkia_order_id": order_id,
        }).insert(ignore_permissions=True)
    else:
        shipment = frappe.get_doc("Shipment Tracking Shipment", shipment_name)

    # -----------------------------
    # LINK SALES INVOICE WHEN WEBHOOK ARRIVES FIRST
    # -----------------------------
    if not shipment.sales_invoice:
        sales_invoice = frappe.db.get_value(
            "Sales Invoice",
            {"si_shipkia_order_id": order_id},
            "name"
        )
        if sales_invoice:
            shipment.sales_invoice = sales_invoice

    # -----------------------------
    # CLEAN DATA
    # -----------------------------
    awb_number = first_clean_value(data, "awb_number", "awb")
    stage = first_clean_value(data, "order_stage", "stage", "shipkia_stage")
    status = first_clean_value(data, "order_status", "status", "shipkia_status")
    courier = first_clean_value(data, "courier_partner", "delivery_partner", "courier")
    eta = first_clean_value(data, "estimated_delivery_date", "estimated_delivery")
    delivered = first_clean_value(data, "delivered_date", "delivered_on")

    # -----------------------------
    # UPDATE SHIPMENT
    # -----------------------------
    if status and shipment.shipkia_status != status:
        shipment.shipkia_status = status

    if stage:
        shipment.shipkia_stage = stage

    if awb_number:
        shipment.shipkia_awb_number = awb_number

    if courier:
        shipment.delivery_partner = courier

    if eta:
        shipment.shipkia_estimated_delivery = get_datetime(eta)

    if delivered:
        shipment.shipkia_delivered_on = get_datetime(delivered)

    shipment.raw_latest_response = frappe.as_json(payload)

    # -----------------------------
    # 🧠 SMART DUPLICATE CHECK
    # -----------------------------
    def is_duplicate_event(shipment, status, courier):
        for e in shipment.events or []:
            if (
                e.status == status
                and (e.detail or "").endswith(f"({courier})")
            ):
                return True
        return False

    if status and not is_duplicate_event(shipment, status, courier):
        shipment.append("events", {
            "date_time": frappe.utils.now_datetime(),
            "status": status,
            "detail": f"Updated via webhook ({courier})",
            "location": "",
        })

    shipment.save(ignore_permissions=True)

    # -----------------------------
    # MIRROR TO SALES INVOICE
    # -----------------------------
    mirror_summary_fields(
        shipment,
        sales_invoice=shipment.sales_invoice,
        encounter_name=shipment.patient_encounter,
    )

    frappe.db.commit()

    return {
        "success": True,
        "message": f"Shipment updated for order {order_id}"
    }
