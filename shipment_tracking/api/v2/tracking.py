"""New OMS manual tracking adapter."""
from types import SimpleNamespace

from .client import get_order_details, get_tracking
from .responses import order_details_from_response, tracking_from_response
from .tracking_params import build_refresh_request


def build_request(shipment, account):
    if account.platform != "New OMS":
        raise ValueError("V2 tracking requires a New OMS account.")
    return build_refresh_request(shipment)


def send(account, request_data):
    order_id = request_data["order_id"]
    details_response, details_body = get_order_details(account, order_id)
    tracking_id = request_data.get("tracking_id")

    if details_response.status_code in (200, 201, 202):
        details = order_details_from_response(details_body, order_id)
        tracking_id = tracking_id or details.get("tracking_id") or details.get("awb")
        if not tracking_id:
            return details_response, {"order_details_response": details_body}

        tracking_response, tracking_body = get_tracking(account, tracking_id)
        combined = {
            "order_details_response": details_body,
            "tracking_response": tracking_body,
        }
        if tracking_response.status_code in (200, 201, 202):
            return tracking_response, combined

        combined["tracking_warning"] = (
            "Order details were loaded, but the tracking timeline is not available yet."
        )
        return SimpleNamespace(status_code=details_response.status_code), combined

    if tracking_id:
        return get_tracking(account, tracking_id)
    return details_response, {"order_details_response": details_body}


def _terminal_state(data):
    value = str(data.get("status") or data.get("stage") or "").strip().casefold()
    return value in {
        "cancelled",
        "canceled",
        "delivered",
        "returned",
        "rto delivered",
        "return delivered",
    }


def _newer_or_equal(left, right):
    from shipment_tracking.services.tracking import site_datetime

    left_time = site_datetime(left)
    right_time = site_datetime(right)
    if not left_time:
        return False
    return not right_time or left_time >= right_time


def _combined_tracking_data(body, shipment):
    details = order_details_from_response(
        body.get("order_details_response"),
        shipment.shipkia_order_id,
    )
    tracking_body = body.get("tracking_response")
    if not isinstance(tracking_body, dict) or tracking_body.get("success") is not True:
        return details

    tracking = tracking_from_response(
        tracking_body,
        shipment.shipkia_order_id,
    )
    details_wins = _terminal_state(details) or _newer_or_equal(
        details.get("status_time"),
        tracking.get("status_time"),
    )
    if details_wins:
        merged = dict(tracking)
        for fieldname in (
            "tracking_id",
            "awb",
            "stage",
            "status",
            "status_detail",
            "courier_partner",
            "courier_mode",
            "estimated_delivery",
            "delivered_on",
            "status_time",
        ):
            if details.get(fieldname) not in (None, ""):
                merged[fieldname] = details[fieldname]
        return merged

    merged = dict(details)
    for fieldname, value in tracking.items():
        if value not in (None, "", []):
            merged[fieldname] = value
    return merged


def parse_response(body, shipment):
    if isinstance(body, dict) and "tracking_response" in body:
        return _combined_tracking_data(body, shipment)
    if isinstance(body, dict) and "order_details_response" in body:
        return order_details_from_response(
            body.get("order_details_response"),
            shipment.shipkia_order_id,
        )
    return tracking_from_response(body, shipment.shipkia_order_id)


def _redact_order_details(body):
    if not isinstance(body, dict):
        return body
    redacted = dict(body)
    result = redacted.get("result")
    if isinstance(result, dict):
        result = dict(result)
        value = result.get("value")
        if isinstance(value, dict):
            value = dict(value)
            for fieldname in tuple(value):
                if fieldname.startswith("delivery_"):
                    value.pop(fieldname, None)
            result["value"] = value
        order_details = result.get("order_details")
        if isinstance(order_details, dict):
            order_details = dict(order_details)
            order_details.pop("delivery_address", None)
            result["order_details"] = order_details
        redacted["result"] = result
    return redacted


def response_for_storage(body):
    if not isinstance(body, dict):
        return body
    if "order_details_response" in body or "tracking_response" in body:
        stored = dict(body)
        if "order_details_response" in stored:
            stored["order_details_response"] = _redact_order_details(
                stored["order_details_response"]
            )
        if "tracking_response" in stored:
            stored["tracking_response"] = _redact_order_details(
                stored["tracking_response"]
            )
        return stored
    return _redact_order_details(body)
