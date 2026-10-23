"""Provider-neutral helpers for parsing inbound webhook payloads."""


def extract_webhook_body(payload):
    if isinstance(payload, list):
        payload = payload[0] if payload else {}

    if isinstance(payload, dict) and isinstance(payload.get("body"), dict):
        return payload.get("body") or {}

    return payload if isinstance(payload, dict) else {}


def clean(value):
    if value is None:
        return None

    value = str(value).strip()
    return None if value.lower() in ("", "none", "null") else value


def first_clean_value(data, *fieldnames):
    for fieldname in fieldnames:
        value = clean(data.get(fieldname))
        if value:
            return value

    return None