from __future__ import annotations

import frappe


INDEXES = (
    ("Sales Invoice", ["si_shipkia_order_id"], "idx_sales_invoice_shipkia_order_id"),
    ("Sales Invoice", ["si_shipkia_shipment"], "idx_sales_invoice_shipkia_shipment"),
    ("Shipment Tracking Shipment", ["shipkia_order_id"], "idx_shipment_shipkia_order_id"),
    ("Shipment Tracking Shipment", ["sales_invoice"], "idx_shipment_sales_invoice"),
    ("Shipment Tracking Shipment", ["patient"], "idx_shipment_patient"),
    ("Shipment Tracking Shipment", ["normalized_status"], "idx_shipment_normalized_status"),
)


def execute() -> None:
    previous = getattr(frappe.flags, "in_migrate", False)
    frappe.flags.in_migrate = True
    try:
        for doctype, fields, index_name in INDEXES:
            add_index_if_ready(doctype, fields, index_name)
    finally:
        frappe.flags.in_migrate = previous


def add_index_if_ready(doctype: str, fields: list[str], index_name: str) -> None:
    if not frappe.db.exists("DocType", doctype):
        return
    if not all(frappe.db.has_column(doctype, fieldname) for fieldname in fields):
        return
    if has_index_for_fields(doctype, fields):
        return
    frappe.db.add_index(doctype, fields, index_name=index_name)


def has_index_for_fields(doctype: str, fields: list[str]) -> bool:
    rows = frappe.db.sql(
        """
        select index_name, group_concat(column_name order by seq_in_index) as indexed_fields
        from information_schema.statistics
        where table_schema = database()
          and table_name = %(table_name)s
        group by index_name
        """,
        {"table_name": f"tab{doctype}"},
        as_dict=True,
    )
    expected = ",".join(fields)
    return any(row.indexed_fields == expected for row in rows)
