"""Legacy Shipkia manual tracking adapter."""
import requests

from shipment_tracking.api.legacy_utils import (
    latest_timeline_entry,
    make_auth_headers,
    safe_response_json,
    tracking_result,
)


def build_request(shipment, account):
    if account.platform != "Legacy":
        raise ValueError("Legacy tracking requires a Legacy account.")
    return {"order_id": shipment.shipkia_order_id}


def send(account, request_data):
    response = requests.post(
        account.order_tracking_url,
        headers=make_auth_headers(account),
        json=request_data,
        timeout=60,
    )
    return response, safe_response_json(response)


def parse_response(body, shipment):
    result = tracking_result(body)
    if not result:
        if isinstance(body, dict) and body.get("raw_text"):
            raise ValueError(
                "Tracking URL returned non-JSON/HTML content. Configure the Legacy API endpoint, "
                "not the public tracking page."
            )
        raise ValueError("Tracking response did not contain result payload.")

    order_details = result.get("order_details") or {}
    latest = latest_timeline_entry(result)
    timeline = []
    for row in result.get("shipment_timeline") or []:
        timeline.append({
            "date_time": row.get("date_time") or row.get("status_time"),
            "status": row.get("status"),
            "detail": row.get("detail") or row.get("instructions"),
            "location": row.get("location"),
        })

    return {
        "company": result.get("company"),
        "company_id": result.get("company_id"),
        "tracking_id": result.get("tracking_id"),
        "awb": order_details.get("awb_number") or order_details.get("awb"),
        "stage": result.get("order_stage") or order_details.get("order_stage") or latest.get("stage"),
        "status": result.get("status") or latest.get("status"),
        "status_detail": latest.get("detail") or latest.get("instructions"),
        "payment_mode": order_details.get("payment_mode"),
        "courier_partner": order_details.get("delivery_partner") or order_details.get("courier_partner"),
        "delivery_location": order_details.get("delivery_location"),
        "estimated_delivery": result.get("estimated_delivery") or order_details.get("estimated_delivery_date"),
        "delivered_on": result.get("delivered_on") or order_details.get("delivered_date"),
        "status_time": latest.get("date_time") or latest.get("status_time"),
        "timeline": timeline,
    }


def response_for_storage(body):
    return body
