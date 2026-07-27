from __future__ import annotations

import frappe


def execute() -> None:
    stored = frappe.db.sql(
        """
        select field
        from tabSingles
        where doctype = 'Shipment Tracking Settings'
          and field = 'enable_default_interakt_fallback'
        limit 1
        """
    )
    if not stored:
        frappe.db.set_single_value(
            "Shipment Tracking Settings",
            "enable_default_interakt_fallback",
            0,
        )
