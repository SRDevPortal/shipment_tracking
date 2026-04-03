from __future__ import annotations

import json
from typing import Any

import frappe
from frappe.utils import cstr, flt, get_datetime


TERMINAL_STATUSES = {"Delivered", "RTO", "Cancelled"}
ACTIVE_SYNC_DEFAULT_LIMIT = 100
TRACKING_STATUS_MAP = {
    "pickup scheduled": "Pending Pickup",
    "picked up": "Picked Up",
    "in transit": "In Transit",
    "reached destination hub": "In Transit",
    "out for delivery": "Out for Delivery",
    "delivered": "Delivered",
    "rto": "RTO",
    "cancelled": "Cancelled",
}


def get_settings():
    return frappe.get_single("Shipment Tracking Settings")


def make_auth_headers(settings) -> dict[str, str]:
    api_key = settings.get_password("api_key", raise_exception=False) or ""
    api_secret = settings.get_password("api_secret", raise_exception=False) or ""
    headers = {"Content-Type": "application/json"}
    if api_key and api_secret:
        headers["Authorization"] = f"token {api_key}:{api_secret}"
    return headers


def safe_json(value: Any) -> str:
    return json.dumps(value, indent=2, default=str)


def first_order_id(body):
    if not isinstance(body, dict):
        return None

    message = body.get("message") or {}

    if isinstance(message, dict):
        docs = message.get("docs") or []
        if isinstance(docs, list) and docs:
            return docs[0].get("name")

    return None


def tracking_result(response_json: dict[str, Any]) -> dict[str, Any]:
    return response_json.get("result") or {}


def latest_timeline_entry(result: dict[str, Any]) -> dict[str, Any]:
    timeline = result.get("shipment_timeline") or []
    if not timeline:
        return {}
    return timeline[0]


def normalize_tracking_status(status: str | None) -> str:
    raw = cstr(status or "").strip()
    if not raw:
        return ""
    return TRACKING_STATUS_MAP.get(raw.lower(), raw)


def safe_response_json(response) -> dict[str, Any]:
    try:
        body = response.json()
        return body if isinstance(body, dict) else {"raw": body}
    except Exception:
        return {"raw_text": getattr(response, "text", "")}


def update_doc_if_exists(doctype: str, name: str | None, values: dict[str, Any]) -> None:
    if not name:
        return
    if not frappe.db.exists(doctype, name):
        return
    frappe.db.set_value(doctype, name, values, update_modified=False)


def dedupe_event_key(row: dict[str, Any]) -> str:
    return "|".join(
        [
            cstr(row.get("date_time")),
            cstr(row.get("status")),
            cstr(row.get("detail")),
            cstr(row.get("location")),
        ]
    )


def as_datetime(value):
    if not value:
        return None
    return get_datetime(value)


def as_float(value) -> float:
    return flt(value or 0)
