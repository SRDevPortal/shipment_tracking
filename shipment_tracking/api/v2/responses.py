"""Validate and extract values from New OMS API responses."""
from datetime import datetime


def order_id_from_response(body, path):
    current = body
    for part in (path or "").split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return (
        str(current)
        if isinstance(current, (str, int))
        and not isinstance(current, bool)
        and str(current).strip()
        else None
    )


def _timeline_datetime(row):
    value = row.get("status_time") or row.get("date_time")
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return datetime.min



def order_details_from_response(body, expected_order_id):
    if not isinstance(body, dict) or body.get("success") is not True:
        raise ValueError("Shipkia order-details response was unsuccessful.")
    result = body.get("result")
    value = result.get("value") if isinstance(result, dict) else None
    if not isinstance(value, dict):
        raise ValueError("Shipkia order-details response did not contain an order.")

    returned_order_id = str(value.get("id") or "").strip()
    if not returned_order_id:
        raise ValueError("Shipkia order-details response did not contain an order ID.")
    if expected_order_id and returned_order_id != str(expected_order_id):
        raise ValueError("Shipkia order-details response order ID does not match the shipment.")

    return {
        "tracking_id": value.get("awb"),
        "awb": value.get("awb"),
        "stage": value.get("stage"),
        "status": value.get("status"),
        "courier_partner": value.get("courier_partner"),
        "courier_mode": value.get("courier_mode"),
        "status_time": value.get("updated_at"),
        "timeline": [],
    }

def tracking_from_response(body, expected_order_id):
    if not isinstance(body, dict) or body.get("success") is not True:
        raise ValueError("Shipkia tracking response was unsuccessful.")
    result = body.get("result")
    if not isinstance(result, dict):
        raise ValueError("Shipkia tracking response did not contain a result.")

    order_details = result.get("order_details")
    if not isinstance(order_details, dict):
        raise ValueError("Shipkia tracking response did not contain order details.")

    returned_order_id = str(order_details.get("id") or "").strip()
    if not returned_order_id:
        raise ValueError("Shipkia tracking response did not contain an order ID.")
    if expected_order_id and returned_order_id != str(expected_order_id):
        raise ValueError("Shipkia tracking response order ID does not match the shipment.")

    source_timeline = result.get("shipment_timeline") or []
    if not isinstance(source_timeline, list):
        raise ValueError("Shipkia tracking timeline has an invalid format.")
    valid_rows = [row for row in source_timeline if isinstance(row, dict)]
    latest = max(valid_rows, key=_timeline_datetime) if valid_rows else {}

    timeline = [{
        "date_time": row.get("status_time") or row.get("date_time"),
        "status": row.get("status"),
        "detail": row.get("instructions") or row.get("detail"),
        "location": row.get("location"),
    } for row in valid_rows]

    return {
        "company": result.get("company"),
        "company_id": result.get("company_id"),
        "tracking_id": result.get("tracking_id"),
        "awb": order_details.get("awb"),
        "stage": latest.get("stage"),
        "status": latest.get("status"),
        "status_detail": latest.get("instructions") or latest.get("detail"),
        "courier_partner": order_details.get("courier_partner"),
        "estimated_delivery": order_details.get("estimated_delivery_date"),
        "delivered_on": order_details.get("delivered_date"),
        "status_time": latest.get("status_time") or latest.get("date_time"),
        "timeline": timeline,
    }
