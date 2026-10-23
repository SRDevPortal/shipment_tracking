from __future__ import annotations

import frappe
from frappe.utils import get_datetime

from .legacy_utils import validate_webhook_secret
from shipment_tracking.services.statuses import normalize_tracking_status
from .webhook_utils import clean, extract_webhook_body, first_clean_value
from .accounts import legacy_settings, LEGACY_ACCOUNT
from .tracking import repair_shipment_links
from shipment_tracking.services.shipments import mirror_summary_fields


@frappe.whitelist(allow_guest=True, methods=["POST"])
def order_status_update():
    """
    Receives webhook from n8n → updates Shipment Tracking Shipment
    """

    # -----------------------------
    # 🔐 SECURITY (WITH TOGGLE)
    # -----------------------------
    settings = legacy_settings()

    validate_webhook_secret(settings)

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
    # GET / CREATE SHIPMENT AND LINKS
    # -----------------------------
    si = None
    encounter = None
    matches = frappe.get_all("Shipment Tracking Shipment", filters={"shipkia_account": LEGACY_ACCOUNT, "shipkia_order_id": order_id}, pluck="name", limit=2)
    if len(matches) != 1:
        frappe.throw("Webhook order ownership is missing or ambiguous; review the shipment.")
    shipment = frappe.get_doc("Shipment Tracking Shipment", matches[0])
    if shipment.sales_invoice:
        si = frappe.get_doc("Sales Invoice", shipment.sales_invoice)
    if shipment.patient_encounter:
        encounter = frappe.get_doc("Patient Encounter", shipment.patient_encounter)

    repair_shipment_links(shipment, si=si, encounter=encounter, order_id=order_id)

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
    shipment.normalized_status = normalize_tracking_status(shipment.shipkia_status)

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
