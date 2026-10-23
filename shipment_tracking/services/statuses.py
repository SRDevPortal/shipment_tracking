"""Provider-neutral status, serialization, and document helpers."""
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
    "pickup completed": "Picked Up",
    "in transit": "In Transit",
    "reached destination hub": "In Transit",
    "out for delivery": "Out for Delivery",
    "ofd": "Out for Delivery",
    "delivered": "Delivered",
    "rto": "RTO",
    "cancelled": "Cancelled",
}


def safe_json(value: Any) -> str:
    return json.dumps(value, indent=2, default=str)


def normalize_tracking_status(status: str | None) -> str:
    raw = cstr(status or "").strip()
    if not raw:
        return ""
    return TRACKING_STATUS_MAP.get(raw.lower(), raw)


def update_doc_if_exists(doctype: str, name: str | None, values: dict[str, Any]) -> None:
    if not name:
        return
    if not frappe.db.exists(doctype, name):
        return
    frappe.db.set_value(doctype, name, values, update_modified=False)


def dedupe_event_key(row: dict[str, Any]) -> str:
    return "|".join([
        cstr(row.get("date_time")),
        cstr(row.get("status")),
        cstr(row.get("detail")),
        cstr(row.get("location")),
    ])


def as_datetime(value):
    if not value:
        return None
    return get_datetime(value)


def as_float(value) -> float:
    return flt(value or 0)