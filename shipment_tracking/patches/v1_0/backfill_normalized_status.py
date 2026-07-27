from __future__ import annotations

from collections import defaultdict

import frappe

from shipment_tracking.api.utils import normalize_tracking_status


BATCH_SIZE = 500


def execute() -> None:
    if not frappe.db.exists("DocType", "Shipment Tracking Shipment"):
        return
    if not frappe.db.has_column("Shipment Tracking Shipment", "normalized_status"):
        return

    while True:
        rows = frappe.db.sql(
            """
            select name, shipkia_status
            from `tabShipment Tracking Shipment`
            where coalesce(normalized_status, '') = ''
              and coalesce(shipkia_status, '') <> ''
            order by name
            limit %(limit)s
            """,
            {"limit": BATCH_SIZE},
            as_dict=True,
        )
        if not rows:
            break

        names_by_status: dict[str, list[str]] = defaultdict(list)
        for row in rows:
            names_by_status[normalize_tracking_status(row.shipkia_status)].append(row.name)

        for normalized_status, names in names_by_status.items():
            frappe.db.set_value(
                "Shipment Tracking Shipment",
                {"name": ["in", names]},
                "normalized_status",
                normalized_status,
                update_modified=False,
            )
        frappe.db.commit()
