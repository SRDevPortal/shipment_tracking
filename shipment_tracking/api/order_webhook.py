from __future__ import annotations

import frappe
from frappe.utils import get_datetime


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
    data = frappe.request.get_json() or {}

    order_id = data.get("order_id")
    if not order_id:
        return {
            "success": False,
            "message": "order_id is required",
            "data": data
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
    # CLEAN DATA
    # -----------------------------
    def clean(value):
        return None if value in ("None", "", None) else value

    awb_number = clean(data.get("awb_number"))
    status = clean(data.get("order_status"))
    courier = clean(data.get("courier_partner"))
    eta = clean(data.get("estimated_delivery_date"))
    delivered = clean(data.get("delivered_date"))

    # -----------------------------
    # UPDATE SHIPMENT
    # -----------------------------
    if status and shipment.shipkia_status != status:
        shipment.shipkia_status = status

    if awb_number:
        shipment.shipkia_awb_number = awb_number

    if courier:
        shipment.delivery_partner = courier

    if eta:
        shipment.shipkia_estimated_delivery = get_datetime(eta)

    if delivered:
        shipment.shipkia_delivered_on = get_datetime(delivered)

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
    if shipment.sales_invoice:
        frappe.db.set_value(
            "Sales Invoice",
            shipment.sales_invoice,
            {
                "si_shipkia_status": shipment.shipkia_status,
                "si_shipkia_awb_number": shipment.shipkia_awb_number,
                "si_shipkia_estimated_delivery": shipment.shipkia_estimated_delivery,
                "si_shipkia_delivered_on": shipment.shipkia_delivered_on,
            },
            update_modified=False
        )

    frappe.db.commit()

    return {
        "success": True,
        "message": f"Shipment updated for order {order_id}"
    }