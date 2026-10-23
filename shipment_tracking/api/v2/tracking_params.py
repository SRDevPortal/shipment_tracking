"""Build New OMS tracking and order-details request parameters."""
import frappe


def resolve_order_id(shipment):
    order_id = (shipment.shipkia_order_id or "").strip()
    if not order_id:
        frappe.throw("Shipment has no Shipkia Order ID.")
    return order_id


def resolve_tracking_id(shipment):
    tracking_id = (shipment.shipkia_tracking_id or shipment.shipkia_awb_number or "").strip()
    if not tracking_id:
        frappe.local.response["http_status_code"] = 409
        frappe.throw(
            "Tracking is not available yet because Shipkia has not assigned a tracking ID or AWB."
        )
    return tracking_id


def optional_tracking_id(shipment):
    return (shipment.shipkia_tracking_id or shipment.shipkia_awb_number or "").strip() or None


def build_tracking_params(shipment):
    return {"tracking_id": resolve_tracking_id(shipment)}


def build_refresh_request(shipment):
    return {
        "order_id": resolve_order_id(shipment),
        "tracking_id": optional_tracking_id(shipment),
    }
