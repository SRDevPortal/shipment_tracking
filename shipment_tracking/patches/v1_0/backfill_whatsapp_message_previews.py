import frappe

from shipment_tracking.notifications import (
    invoice_template_preview,
    shipment_template_preview,
)


BATCH_SIZE = 500


def execute():
    while True:
        rows = frappe.db.sql(
            """
            select name, event_type, body_values_json, chat_message
            from `tabShipment WhatsApp Notification`
            where coalesce(body_preview, '') = ''
            order by creation, name
            limit %s
            """,
            (BATCH_SIZE,),
            as_dict=True,
        )
        if not rows:
            break

        for row in rows:
            body_values = frappe.parse_json(row.body_values_json or "[]")
            preview = build_preview(row.event_type, body_values)
            frappe.db.set_value(
                "Shipment WhatsApp Notification",
                row.name,
                "body_preview",
                preview,
                update_modified=False,
            )
            backfill_chat_message(row.chat_message, preview)


def build_preview(event_type: str, body_values: list[str]) -> str:
    if event_type == "sales_invoice_generated":
        return invoice_template_preview(body_values)
    return shipment_template_preview(body_values, event_type)


def backfill_chat_message(chat_message: str | None, preview: str) -> None:
    if not chat_message or not frappe.db.exists("Chat Message", chat_message):
        return
    body = frappe.db.get_value("Chat Message", chat_message, "body") or ""
    if not body.startswith("Template:"):
        return
    frappe.db.set_value(
        "Chat Message",
        chat_message,
        "body",
        preview,
        update_modified=False,
    )
