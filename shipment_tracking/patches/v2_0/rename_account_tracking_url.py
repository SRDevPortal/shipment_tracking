"""Rename the per-account tracking endpoint without losing configured URLs."""
import frappe


def execute():
    doctype = "Shipkia Account"
    if not frappe.db.table_exists(doctype):
        return
    if not frappe.db.has_column(doctype, "order_tracking_url"):
        frappe.db.sql(
            "alter table `tabShipkia Account` "
            "add column `order_tracking_url` longtext"
        )
    if frappe.db.has_column(doctype, "tracking_url"):
        frappe.db.sql(
            """update `tabShipkia Account`
               set order_tracking_url = tracking_url
             where coalesce(order_tracking_url, '') = ''
               and coalesce(tracking_url, '') != ''"""
        )
