"""UI-safe result objects for Shipkia order creation."""
from __future__ import annotations
import html
import re
from typing import Any

_TAG_RE = re.compile(r"<[^>]*>")
_SPACE_RE = re.compile(r"\s+")
_MESSAGE_KEYS = ("message", "error", "detail", "description")

def safe_text(value: Any, limit: int = 500) -> str:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return ""
    text = _TAG_RE.sub(" ", html.unescape(str(value)))
    return _SPACE_RE.sub(" ", text).strip()[:limit]

def _messages(value: Any, output: list[str], depth: int = 0) -> None:
    if depth > 3 or len(output) >= 8:
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _MESSAGE_KEYS:
                message = safe_text(item)
                if message:
                    output.append(message)
            elif key in ("errors", "validation_errors", "data"):
                _messages(item, output, depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _messages(item, output, depth + 1)
    else:
        message = safe_text(value)
        if message:
            output.append(message)

def provider_summary(body: Any, fallback: str) -> dict[str, Any]:
    messages: list[str] = []
    if isinstance(body, dict):
        for key in _MESSAGE_KEYS:
            message = safe_text(body.get(key))
            if message:
                messages.append(message)
        for key in ("errors", "validation_errors"):
            _messages(body.get(key), messages)
    unique = list(dict.fromkeys(messages))[:8]
    trace_id = safe_text(body.get("traceId") or body.get("trace_id"), 120) if isinstance(body, dict) else ""
    return {"message": unique[0] if unique else fallback,
            "validation_messages": unique[1:], "provider_trace_id": trace_id}

def result(outcome: str, title: str, message: str, **values) -> dict[str, Any]:
    output = {
        "success": False, "outcome": outcome, "title": safe_text(title, 120),
        "message": safe_text(message), "request_sent": False, "retry_allowed": False,
        "account": "", "order_id": "", "shipment": "", "sync_log": "",
        "provider_status": "", "validation_messages": [], "provider_trace_id": "",
    }
    for key in ("success", "request_sent", "retry_allowed"):
        if key in values:
            output[key] = bool(values[key])
    for key in ("account", "order_id", "shipment", "sync_log", "provider_status", "provider_trace_id"):
        output[key] = safe_text(values.get(key), 140)
    output["validation_messages"] = [
        safe_text(item) for item in values.get("validation_messages", []) if safe_text(item)
    ][:8]
    return output

def local_validation(message: str) -> dict[str, Any]:
    return result("local_validation_failed", "Order Could Not Be Created", message,
                  retry_allowed=True)
