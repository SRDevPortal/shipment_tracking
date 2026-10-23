"""Compatibility imports; new code should use api.legacy_utils or services.statuses."""
from shipment_tracking.api.legacy_utils import (
    first_order_id,
    get_settings,
    latest_timeline_entry,
    make_auth_headers,
    safe_response_json,
    tracking_result,
    validate_webhook_secret,
)
from shipment_tracking.services.statuses import (
    ACTIVE_SYNC_DEFAULT_LIMIT,
    TERMINAL_STATUSES,
    TRACKING_STATUS_MAP,
    as_datetime,
    as_float,
    dedupe_event_key,
    normalize_tracking_status,
    safe_json,
    update_doc_if_exists,
)

__all__ = [
    "ACTIVE_SYNC_DEFAULT_LIMIT", "TERMINAL_STATUSES", "TRACKING_STATUS_MAP",
    "as_datetime", "as_float", "dedupe_event_key", "first_order_id",
    "get_settings", "latest_timeline_entry", "make_auth_headers",
    "normalize_tracking_status", "safe_json", "safe_response_json",
    "tracking_result", "update_doc_if_exists", "validate_webhook_secret",
]