"""Indexes for account-owned shipment and operational-log queries."""

import frappe

from shipment_tracking.patches.v1_0.add_tracking_indexes import add_index_if_ready


INDEXES = (
    (
        "Shipment Tracking Shipment",
        ["shipkia_account", "shipkia_order_id"],
        "idx_shipment_account_order",
    ),
    (
        "Shipment Tracking Shipment",
        ["shipkia_account", "normalized_status"],
        "idx_shipment_account_status",
    ),
    (
        "Shipment Tracking Sync Log",
        ["action", "status", "creation"],
        "idx_sync_log_action_status_creation",
    ),
    (
        "Shipment Tracking Sync Log",
        ["shipkia_account", "shipkia_order_id", "creation"],
        "idx_sync_log_account_order_creation",
    ),
)


def execute():
    previous = getattr(frappe.flags, "in_migrate", False)
    frappe.flags.in_migrate = True
    try:
        for doctype, fields, index_name in INDEXES:
            add_index_if_ready(doctype, fields, index_name)
    finally:
        frappe.flags.in_migrate = previous
