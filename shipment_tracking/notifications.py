from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import add_to_date, cint, cstr, flt, format_date, format_datetime, now_datetime

from shipment_tracking.api.utils import normalize_tracking_status, safe_json


NOTIFICATION_DOCTYPE = "Shipment WhatsApp Notification"
EVENT_CONFIG = {
    "sales_invoice_generated": {
        "enable_field": "enable_sales_invoice_generated",
        "template_field": "sales_invoice_generated_template",
        "language_field": "sales_invoice_generated_language",
    },
    "order_picked_up": {
        "enable_field": "enable_order_picked_up",
        "template_field": "order_picked_up_template",
        "language_field": "order_picked_up_language",
    },
    "out_for_delivery": {
        "enable_field": "enable_out_for_delivery",
        "template_field": "out_for_delivery_template",
        "language_field": "out_for_delivery_language",
    },
}
STATUS_EVENT_MAP = {
    "Picked Up": "order_picked_up",
    "Out for Delivery": "out_for_delivery",
}
RETRY_BATCH_SIZE = 50
ERROR_MESSAGE_LIMIT = 4000


def on_sales_invoice_submit(doc, method=None) -> None:
    try:
        if doc.docstatus != 1 or not cstr(getattr(doc, "patient", "")).strip():
            return
        body_values = invoice_template_values(doc)
        create_notification(
            event_type="sales_invoice_generated",
            patient=doc.patient,
            sales_invoice=doc.name,
            body_values=body_values,
            body_preview=invoice_template_preview(body_values),
        )
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"Shipment WhatsApp invoice notification failed for {doc.name}",
        )


def notify_shipment_status_transition(shipment, previous_status: str | None) -> str | None:
    previous_normalized = normalize_tracking_status(previous_status)
    current_normalized = normalize_tracking_status(
        getattr(shipment, "normalized_status", None) or getattr(shipment, "shipkia_status", None)
    )
    if not current_normalized or current_normalized == previous_normalized:
        return None

    event_type = STATUS_EVENT_MAP.get(current_normalized)
    if not event_type:
        return None

    try:
        body_values = shipment_template_values(shipment, event_type)
        return create_notification(
            event_type=event_type,
            patient=getattr(shipment, "patient", None),
            sales_invoice=getattr(shipment, "sales_invoice", None),
            shipment=shipment.name,
            shipkia_order_id=getattr(shipment, "shipkia_order_id", None),
            body_values=body_values,
            body_preview=shipment_template_preview(body_values, event_type),
        )
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"Shipment WhatsApp status notification failed for {shipment.name}",
        )
        return None


def create_notification(
    *,
    event_type: str,
    patient: str | None,
    body_values: list[str],
    body_preview: str,
    sales_invoice: str | None = None,
    shipment: str | None = None,
    shipkia_order_id: str | None = None,
) -> str | None:
    settings = frappe.get_cached_doc("Shipment Tracking Settings")
    if not is_event_enabled(settings, event_type, patient=patient):
        return None

    config = EVENT_CONFIG[event_type]
    event_key = build_event_key(
        event_type,
        sales_invoice=sales_invoice,
        shipment=shipment,
    )
    existing = frappe.db.get_value(NOTIFICATION_DOCTYPE, {"event_key": event_key}, "name")
    if existing:
        return existing

    dry_run = bool(cint(getattr(settings, "whatsapp_dry_run", 0)))
    notification = frappe.get_doc(
        {
            "doctype": NOTIFICATION_DOCTYPE,
            "event_key": event_key,
            "event_type": event_type,
            "status": "Skipped" if dry_run else "Queued",
            "sales_invoice": sales_invoice,
            "shipment": shipment,
            "patient": patient,
            "shipkia_order_id": shipkia_order_id,
            "template_name": cstr(getattr(settings, config["template_field"], "")).strip(),
            "language_code": cstr(getattr(settings, config["language_field"], "")).strip(),
            "body_values_json": safe_json(body_values),
            "body_preview": cstr(body_preview),
            "queued_on": now_datetime(),
            "skip_reason": "Dry run is enabled." if dry_run else None,
        }
    )

    savepoint = "shipment_whatsapp_notification_insert"
    frappe.db.savepoint(savepoint)
    try:
        notification.insert(ignore_permissions=True)
        frappe.db.release_savepoint(savepoint)
    except frappe.DuplicateEntryError:
        frappe.db.rollback(save_point=savepoint)
        return frappe.db.get_value(NOTIFICATION_DOCTYPE, {"event_key": event_key}, "name")

    if not dry_run:
        enqueue_notification(notification.name, enqueue_after_commit=True)
    return notification.name


def build_event_key(
    event_type: str,
    *,
    sales_invoice: str | None = None,
    shipment: str | None = None,
) -> str:
    if event_type == "sales_invoice_generated":
        if not sales_invoice:
            raise ValueError("Sales Invoice is required for sales_invoice_generated.")
        return f"sales_invoice:{sales_invoice}:{event_type}"
    if not shipment:
        raise ValueError(f"Shipment is required for {event_type}.")
    return f"shipment:{shipment}:{event_type}"


def is_event_enabled(settings, event_type: str, patient: str | None = None) -> bool:
    config = EVENT_CONFIG.get(event_type)
    engine = cstr(getattr(settings, "whatsapp_notification_engine", "")).strip()
    if engine and engine != "Legacy Shipment Tracking":
        return False
    if not config or not cint(getattr(settings, "enable_whatsapp_notifications", 0)):
        return False
    if not cint(getattr(settings, config["enable_field"], 0)):
        return False
    pilot_patient = cstr(getattr(settings, "whatsapp_test_patient", "")).strip()
    return not pilot_patient or pilot_patient == cstr(patient).strip()


def enqueue_notification(notification_name: str, *, enqueue_after_commit: bool) -> None:
    frappe.enqueue(
        "shipment_tracking.notifications.send_notification",
        queue="short",
        timeout=90,
        enqueue_after_commit=enqueue_after_commit,
        job_id=f"shipment_whatsapp_{notification_name}",
        deduplicate=True,
        notification_name=notification_name,
    )


def send_notification(notification_name: str) -> dict[str, Any]:
    notification = frappe.get_doc(NOTIFICATION_DOCTYPE, notification_name)
    if notification.status in {"Sent", "Skipped", "Sending"}:
        return {"success": notification.status == "Sent", "status": notification.status}

    settings = frappe.get_cached_doc("Shipment Tracking Settings")
    if not is_event_enabled(settings, notification.event_type, patient=notification.patient):
        mark_skipped(notification, "Notification disabled in Shipment Tracking Settings.")
        return {"success": False, "status": "Skipped"}
    if cint(getattr(settings, "whatsapp_dry_run", 0)):
        mark_skipped(notification, "Dry run is enabled.")
        return {"success": False, "status": "Skipped"}

    maximum_attempts = max(cint(getattr(settings, "whatsapp_max_retries", 3)), 1)
    if cint(notification.attempt_count) >= maximum_attempts:
        notification.status = "Failed"
        notification.next_retry_on = None
        notification.save(ignore_permissions=True)
        frappe.db.commit()
        return {"success": False, "status": "Failed", "error": "Maximum attempts reached."}

    notification.status = "Sending"
    notification.attempt_count = cint(notification.attempt_count) + 1
    notification.next_retry_on = None
    notification.last_error = None
    notification.save(ignore_permissions=True)
    frappe.db.commit()

    try:
        from wa_chat_hub.automation import send_patient_template

        result = send_patient_template(
            patient=notification.patient,
            template_name=notification.template_name,
            language_code=notification.language_code,
            body_values=frappe.parse_json(notification.body_values_json or "[]"),
            body_preview=notification.body_preview,
            event_key=notification.event_key,
            fallback_channel_account=(
                cstr(getattr(settings, "default_interakt_account", "")).strip()
                if cint(getattr(settings, "enable_default_interakt_fallback", 0))
                else None
            ),
        )
    except Exception as exc:
        mark_failed(notification, settings, exc)
        return {"success": False, "status": "Failed", "error": cstr(exc)}

    notification.status = "Sent"
    notification.conversation = result.get("conversation")
    notification.chat_message = result.get("message")
    notification.provider_message_id = result.get("provider_message_id")
    notification.channel_account = result.get("channel_account")
    notification.routing_source = result.get("routing_source")
    notification.sent_on = now_datetime()
    notification.next_retry_on = None
    notification.last_error = None
    notification.save(ignore_permissions=True)
    frappe.db.commit()
    return {"success": True, "status": "Sent", **result}


def mark_skipped(notification, reason: str) -> None:
    notification.status = "Skipped"
    notification.skip_reason = reason
    notification.next_retry_on = None
    notification.save(ignore_permissions=True)
    frappe.db.commit()


def mark_failed(notification, settings, error: Exception) -> None:
    maximum_attempts = max(cint(getattr(settings, "whatsapp_max_retries", 3)), 1)
    attempt_count = cint(notification.attempt_count)
    base_delay = max(cint(getattr(settings, "whatsapp_retry_delay_minutes", 5)), 1)
    notification.status = "Failed"
    notification.last_error = cstr(error)[:ERROR_MESSAGE_LIMIT]
    notification.next_retry_on = (
        add_to_date(
            now_datetime(),
            minutes=base_delay * (2 ** max(attempt_count - 1, 0)),
            as_datetime=True,
        )
        if attempt_count < maximum_attempts
        else None
    )
    notification.save(ignore_permissions=True)
    frappe.db.commit()
    frappe.log_error(
        frappe.get_traceback(),
        f"Shipment WhatsApp send failed for {notification.name}",
    )


def retry_failed_notifications() -> None:
    settings = frappe.get_cached_doc("Shipment Tracking Settings")
    engine = cstr(getattr(settings, "whatsapp_notification_engine", "")).strip()
    if engine and engine != "Legacy Shipment Tracking":
        return
    if not cint(getattr(settings, "enable_whatsapp_notifications", 0)):
        return
    if cint(getattr(settings, "whatsapp_dry_run", 0)):
        return
    maximum_attempts = max(cint(getattr(settings, "whatsapp_max_retries", 3)), 1)
    rows = frappe.get_all(
        NOTIFICATION_DOCTYPE,
        filters={
            "status": "Failed",
            "next_retry_on": ["<=", now_datetime()],
            "attempt_count": ["<", maximum_attempts],
        },
        fields=["name"],
        order_by="next_retry_on asc",
        limit_page_length=RETRY_BATCH_SIZE,
    )
    for row in rows:
        enqueue_notification(row.name, enqueue_after_commit=False)


def invoice_template_values(invoice) -> list[str]:
    patient_name = cstr(getattr(invoice, "patient_name", "")).strip() or patient_display_name(
        getattr(invoice, "patient", None)
    )
    amount = flt(getattr(invoice, "rounded_total", 0) or getattr(invoice, "grand_total", 0))
    currency = cstr(getattr(invoice, "currency", "")).strip()
    return [
        patient_name,
        cstr(invoice.name),
        format_date(getattr(invoice, "posting_date", None)),
        f"{currency} {amount:.2f}".strip(),
    ]


def shipment_template_values(shipment, event_type: str) -> list[str]:
    values = [
        patient_display_name(getattr(shipment, "patient", None)),
        cstr(getattr(shipment, "shipkia_order_id", "")),
        cstr(getattr(shipment, "shipkia_awb_number", "")),
        cstr(getattr(shipment, "delivery_partner", "")),
    ]
    if event_type == "order_picked_up":
        estimated_delivery = getattr(shipment, "shipkia_estimated_delivery", None)
        values.append(format_datetime(estimated_delivery) if estimated_delivery else "")
    return values


def invoice_template_preview(body_values: list[str]) -> str:
    patient_name, invoice_name, posting_date, amount = body_values
    return "\n".join(
        [
            f"Hello {patient_name},",
            "",
            f"Your sales invoice {invoice_name} dated {posting_date} has been generated successfully.",
            "",
            f"Invoice Amount: {amount}",
            "",
            "Thank you for choosing us.",
        ]
    )


def shipment_template_preview(body_values: list[str], event_type: str) -> str:
    if event_type == "order_picked_up":
        patient_name, order_id, awb_number, delivery_partner, estimated_delivery = body_values
        return "\n".join(
            [
                f"Hello {patient_name},",
                "",
                f"Your order {order_id} has been picked up and is on its way.",
                "",
                f"AWB Number: {awb_number}",
                f"Delivery Partner: {delivery_partner}",
                f"Estimated Delivery: {estimated_delivery}",
                "",
                "We will notify you when it is out for delivery.",
            ]
        )
    if event_type == "out_for_delivery":
        patient_name, order_id, awb_number, delivery_partner = body_values
        return "\n".join(
            [
                f"Hello {patient_name},",
                "",
                f"Your order {order_id} is out for delivery.",
                "",
                f"AWB Number: {awb_number}",
                f"Delivery Partner: {delivery_partner}",
                "",
                "Please keep your phone available for the delivery agent.",
            ]
        )
    raise ValueError(f"Unsupported shipment notification event: {event_type}")


def patient_display_name(patient: str | None) -> str:
    if not patient:
        return ""
    return cstr(frappe.db.get_value("Patient", patient, "patient_name") or patient)
