from __future__ import annotations

import frappe


DEFAULTS = {
    "enable_whatsapp_notifications": 0,
    "whatsapp_dry_run": 1,
    "enable_sales_invoice_generated": 0,
    "enable_order_picked_up": 0,
    "enable_out_for_delivery": 0,
    "enable_default_interakt_fallback": 0,
    "sales_invoice_generated_template": "sales_invoice_generated",
    "sales_invoice_generated_language": "en",
    "order_picked_up_template": "order_picked_up",
    "order_picked_up_language": "en",
    "out_for_delivery_template": "out_for_delivery",
    "out_for_delivery_language": "en",
    "whatsapp_max_retries": 3,
    "whatsapp_retry_delay_minutes": 5,
}


def execute() -> None:
    for fieldname, value in DEFAULTS.items():
        stored = frappe.db.sql(
            """
            select field
            from tabSingles
            where doctype = %(doctype)s
              and field = %(fieldname)s
            limit 1
            """,
            {
                "doctype": "Shipment Tracking Settings",
                "fieldname": fieldname,
            },
        )
        if not stored:
            frappe.db.set_single_value("Shipment Tracking Settings", fieldname, value)
