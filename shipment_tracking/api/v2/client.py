"""HTTP client for New OMS order and tracking operations."""

from urllib.parse import quote, urlsplit

import frappe
import requests

from .responses import order_id_from_response


def _validated_url(url, purpose):
    if urlsplit(url).scheme != "https" or not urlsplit(url).netloc:
        frappe.throw(f"Configure an HTTPS V2 {purpose} endpoint.")
    return url


def _headers(account):
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "x-api-key": account.get_password("api_key"),
    }


def _json_body(response):
    try:
        body = response.json()
        return body if isinstance(body, dict) else {"error": "Unexpected provider response", "raw": body}
    except ValueError:
        return {"error": "Non-JSON provider response"}


def send(account, payload):
    url = account.create_order_url or (account.api_base_url or "").rstrip("/") + "/oms/orders"
    response = requests.post(
        _validated_url(url, "order"),
        headers=_headers(account),
        json=payload,
        timeout=60,
    )
    body = _json_body(response)
    order_id = (
        order_id_from_response(body, account.v2_order_id_path)
        if body.get("success") is True
        else None
    )
    return response, body, order_id



def get_order_details(account, order_id):
    base_url = (account.order_details_url or "").rstrip("/")
    url = base_url + "/" + quote(str(order_id), safe="")
    response = requests.get(
        _validated_url(url, "order details"),
        headers=_headers(account),
        timeout=60,
    )
    return response, _json_body(response)

def get_tracking(account, tracking_id):
    url = account.order_tracking_url or (
        (account.api_base_url or "").rstrip("/") + "/oms/orders/get_order_tracking"
    )
    response = requests.get(
        _validated_url(url, "tracking"),
        headers=_headers(account),
        params={"tracking_id": tracking_id},
        timeout=60,
    )
    return response, _json_body(response)
