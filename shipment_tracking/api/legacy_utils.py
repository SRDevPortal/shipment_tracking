"""Legacy Shipkia settings, authentication, and response helpers."""
from __future__ import annotations

from typing import Any

import frappe


def get_settings():
    return frappe.get_single("Shipment Tracking Settings")


def validate_webhook_secret(settings=None) -> None:
    settings = settings or get_settings()
    if not getattr(settings, "enable_webhook_security", 0):
        return

    secret = settings.get_password("webhook_secret", raise_exception=False) or ""
    incoming_secret = frappe.get_request_header("X-Webhook-Secret") or ""
    if not secret or incoming_secret != secret:
        frappe.local.response["http_status_code"] = 403
        frappe.throw("Unauthorized request", frappe.PermissionError)


def make_auth_headers(settings) -> dict[str, str]:
    api_key = settings.get_password("api_key", raise_exception=False) or ""
    api_secret = settings.get_password("api_secret", raise_exception=False) or ""
    headers = {"Content-Type": "application/json"}
    if api_key and api_secret:
        headers["Authorization"] = f"token {api_key}:{api_secret}"
    return headers


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
    if not isinstance(response_json, dict):
        return {}

    result = response_json.get("result")
    if isinstance(result, dict):
        return result

    message = response_json.get("message")
    if isinstance(message, dict):
        result = message.get("result")
        if isinstance(result, dict):
            return result
        if any(key in message for key in ("order_details", "shipment_timeline", "status", "order_stage")):
            return message
    return {}


def latest_timeline_entry(result: dict[str, Any]) -> dict[str, Any]:
    timeline = result.get("shipment_timeline") or []
    return timeline[0] if timeline else {}


def safe_response_json(response) -> dict[str, Any]:
    try:
        body = response.json()
        return body if isinstance(body, dict) else {"raw": body}
    except Exception:
        return {"raw_text": getattr(response, "text", "")}