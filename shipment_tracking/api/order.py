from __future__ import annotations

from typing import Any

import frappe
import requests
from frappe.utils import cstr

from .utils import first_order_id, get_settings, make_auth_headers, safe_json, safe_response_json
from .tracking import create_or_update_shipment_from_order_response, get_linked_encounter


@frappe.whitelist()
def create_order_for_sales_invoice(invoice_name: str, force: int = 0):
    si = frappe.get_doc("Sales Invoice", invoice_name)
    if si.docstatus != 1:
        frappe.throw("Sales Invoice must be submitted before sending to Shipkia.")

    settings = get_settings()
    if not settings.enabled:
        frappe.throw("Shipment Tracking is disabled in settings.")

    if cstr(getattr(si, "shipkia_order_id", "")).strip() and not int(force or 0):
        frappe.throw("This Sales Invoice already has a Shipkia Order ID. Use resend only if intentional.")

    payload = build_payload_from_sales_invoice(si, settings)
    log = make_sync_log("Outbound", "Create Order", "Sales Invoice", si.name, payload)

    try:
        response = requests.post(
            settings.create_order_url,
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
        frappe.throw("Shipkia order creation failed. Check Shipment Tracking Sync Log.")

    order_id = first_order_id(body)
    if not order_id:
        log.status = "Failed"
        log.error_message = "Shipkia response did not contain docs[0].name order id."
        log.save(ignore_permissions=True)
        frappe.throw("Shipkia order creation succeeded without a usable order id. Check Sync Log.")

    encounter = get_linked_encounter(si)
    shipment = create_or_update_shipment_from_order_response(si, encounter, order_id, body)

    log.status = "Success"
    log.shipkia_order_id = order_id
    log.save(ignore_permissions=True)

    if getattr(si, "shipkia_order_id", None) != order_id:
        frappe.db.set_value(
            "Sales Invoice",
            si.name,
            {
                "shipkia_order_id": order_id,
                "shipkia_shipment": shipment.name,
            },
            update_modified=False,
        )

    return {
        "success": True,
        "order_id": order_id,
        "shipment": shipment.name,
        "message": f"Shipkia order created: {order_id}",
    }


def build_payload_from_sales_invoice(si, settings) -> dict[str, Any]:
    shipping = get_shipping_address(si)
    billing = get_billing_address(si)
    billing_same_as_delivery = shipping.name == billing.name

    products = []
    for row in si.items:
        if not row.item_code:
            continue
        products.append(
            {
                "product_name": row.item_name,
                "unit_price": row.rate,
                "quantity": row.qty,
                "hsn_code": getattr(row, "gst_hsn_code", "") or "",
                "product_discount": 0,
                "tax_rate": get_tax_rate(si),
                "tax_preference": "Inclusive",
            }
        )

    payload = {
        "pickup_address": settings.pickup_address,
        "delivery_phone_number": normalize_phone(si.contact_mobile),
        "delivery_full_name": si.customer_name,
        "delivery_pincode": shipping.pincode,
        "delivery_address": join_address(shipping),
        "billing_same_as_delivery": billing_same_as_delivery,
        "payment_method": "prepaid" if (si.outstanding_amount or 0) <= 0 else "cod",
        "length": settings.default_parcel_length or 1,
        "breadth": settings.default_parcel_breadth or 1,
        "height": settings.default_parcel_height or 1,
        "dead_weight": settings.default_dead_weight or 0.1,
        "order_channel": settings.order_channel or "Custom",
        "product_details": products,
        "shipping_charges": 0,
        "transaction_charges": 0,
        "gift_wrap": 0,
        "total_discount": getattr(si, "discount_amount", 0) or 0,
        "prepaid_cod_amount": max((si.grand_total or 0) - (si.outstanding_amount or 0), 0),
        "notes": si.remarks or "",
        "tag": f"ERP | SI:{si.name}",
    }

    if not billing_same_as_delivery:
        payload.update(
            {
                "billing_phone_number": normalize_phone(si.contact_mobile),
                "billing_full_name": si.customer_name,
                "billing_pincode": billing.pincode,
                "billing_address": join_address(billing),
            }
        )

    return payload


def make_sync_log(direction: str, action: str, reference_doctype: str, reference_name: str, request_json: dict[str, Any]):
    return frappe.get_doc(
        {
            "doctype": "Shipment Tracking Sync Log",
            "direction": direction,
            "action": action,
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "request_json": safe_json(request_json),
            "status": "Running",
        }
    ).insert(ignore_permissions=True)


def get_shipping_address(si):
    if si.shipping_address_name:
        return frappe.get_doc("Address", si.shipping_address_name)
    if si.customer_address:
        return frappe.get_doc("Address", si.customer_address)
    frappe.throw("No Shipping Address found on Sales Invoice.")


def get_billing_address(si):
    if si.customer_address:
        return frappe.get_doc("Address", si.customer_address)
    if si.shipping_address_name:
        return frappe.get_doc("Address", si.shipping_address_name)
    frappe.throw("No Billing Address found")


def join_address(address_doc) -> str:
    return ", ".join(filter(None, [cstr(address_doc.address_line1), cstr(address_doc.address_line2)]))


def normalize_phone(phone: str | None) -> str:
    phone = cstr(phone or "").strip().replace(" ", "").replace("-", "")
    if phone.startswith("0"):
        phone = phone[1:]
    if phone.startswith("+91"):
        phone = phone[3:]
    elif phone.startswith("91") and len(phone) == 12:
        phone = phone[2:]
    if len(phone) == 10 and phone.isdigit():
        return f"+91-{phone}"
    frappe.throw("Customer mobile number is invalid for Shipkia sync.")


def get_tax_rate(si) -> float:
    for tax in si.taxes or []:
        if (tax.rate or 0) > 0:
            return tax.rate
    return 0
