"""Read-only operational diagnostics for Shipment Tracking administrators."""

import frappe


@frappe.whitelist()
def get_operational_health():
    frappe.only_for("System Manager")

    counts = {
        doctype: frappe.db.count(doctype)
        for doctype in (
            "Shipment Tracking Shipment",
            "Shipment Tracking Sync Log",
            "Shipment Tracking Support Ticket",
            "Shipment WhatsApp Notification",
        )
    }
    shipments_by_account = frappe.db.sql(
        """
        select coalesce(shipkia_account, '<unassigned>') as account, count(*) as count
        from `tabShipment Tracking Shipment`
        group by coalesce(shipkia_account, '<unassigned>')
        order by count desc
        """,
        as_dict=True,
    )
    logs_by_status = frappe.db.sql(
        """
        select status, count(*) as count
        from `tabShipment Tracking Sync Log`
        group by status
        order by count desc
        """,
        as_dict=True,
    )
    duplicate_identity = frappe.db.sql(
        """
        select count(*) as groups_count, coalesce(sum(row_count - 1), 0) as extra_rows
        from (
            select count(*) as row_count
            from `tabShipment Tracking Shipment`
            where coalesce(shipkia_account, '') != ''
              and coalesce(shipkia_order_id, '') != ''
            group by shipkia_account, shipkia_order_id
            having count(*) > 1
        ) duplicates
        """,
        as_dict=True,
    )[0]
    unresolved_attempts = frappe.db.count(
        "Shipment Tracking Sync Log",
        {"status": ["in", ["Running", "Uncertain"]]},
    )

    return {
        "counts": counts,
        "shipments_by_account": shipments_by_account,
        "logs_by_status": logs_by_status,
        "duplicate_identity_groups": int(duplicate_identity.groups_count or 0),
        "duplicate_extra_rows": int(duplicate_identity.extra_rows or 0),
        "unresolved_attempts": unresolved_attempts,
        "generated_on": frappe.utils.now_datetime(),
    }
