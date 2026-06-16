import frappe

from .utils import create_cf_with_module, delete_custom_fields, migrate_custom_field_data

DT = "Sales Invoice"


def apply():
    create_cf_with_module(
        {
            DT: [
                {
                    "fieldname": "source_encounter",
                    "label": "Source Encounter",
                    "fieldtype": "Link",
                    "options": "Patient Encounter",
                    "read_only": 1,
                    "insert_after": "patient_name",
                },
                {
                    "fieldname": "si_shipment_tracking_tab",
                    "label": "Shipment Tracking",
                    "fieldtype": "Tab Break",
                    "insert_after": "terms",
                },
                {
                    "fieldname": "si_shipment_tracking_section",
                    "fieldtype": "Section Break",
                    "insert_after": "si_shipment_tracking_tab",
                    "collapsible": 1,
                },
                {
                    "fieldname": "si_shipkia_order_id",
                    "label": "Shipkia Order ID",
                    "fieldtype": "Data",
                    "read_only": 1,
                    "in_list_view": 1,
                    "in_standard_filter": 1,
                    "insert_after": "si_shipment_tracking_section",
                },
                {
                    "fieldname": "si_shipkia_awb_number",
                    "label": "Shipkia AWB Number",
                    "fieldtype": "Data",
                    "read_only": 1,
                    "in_list_view": 1,
                    "insert_after": "si_shipkia_order_id",
                },
                {
                    "fieldname": "si_shipkia_stage",
                    "label": "Shipkia Stage",
                    "fieldtype": "Data",
                    "read_only": 1,
                    "in_list_view": 1,
                    "insert_after": "si_shipkia_awb_number",
                },
                {
                    "fieldname": "si_shipkia_status",
                    "label": "Shipkia Status",
                    "fieldtype": "Data",
                    "read_only": 1,
                    "in_list_view": 1,
                    "in_standard_filter": 1,
                    "insert_after": "si_shipkia_stage",
                },
                {
                    "fieldname": "si_shipkia_estimated_delivery",
                    "label": "Estimated Delivery",
                    "fieldtype": "Datetime",
                    "read_only": 1,
                    "insert_after": "si_shipkia_status",
                },
                {
                    "fieldname": "si_shipkia_delivered_on",
                    "label": "Delivered On",
                    "fieldtype": "Datetime",
                    "read_only": 1,
                    "insert_after": "si_shipkia_estimated_delivery",
                },
                {
                    "fieldname": "si_delivery_partner",
                    "label": "Courier Partner",
                    "fieldtype": "Data",
                    "read_only": 1,
                    "in_list_view": 1,
                    "insert_after": "si_shipkia_delivered_on",
                },
                {
                    "fieldname": "si_shipkia_shipment",
                    "label": "Shipment Record",
                    "fieldtype": "Link",
                    "options": "Shipment Tracking Shipment",
                    "read_only": 1,
                    "insert_after": "si_delivery_partner",
                },
                {
                    "fieldname": "si_support_ticket_column",
                    "fieldtype": "Column Break",
                    "insert_after": "si_shipkia_shipment",
                },
                {
                    "fieldname": "si_support_actions_html",
                    "label": "Support Actions",
                    "fieldtype": "HTML",
                    "insert_after": "si_support_ticket_column",
                },
                {
                    "fieldname": "si_latest_support_ticket",
                    "label": "Latest Support Ticket",
                    "fieldtype": "Link",
                    "options": "Shipment Tracking Support Ticket",
                    "read_only": 1,
                    "hidden": 1,
                    "insert_after": "si_support_actions_html",
                },
                {
                    "fieldname": "si_latest_support_ticket_id",
                    "label": "Latest Support Ticket ID",
                    "fieldtype": "Data",
                    "read_only": 1,
                    "hidden": 1,
                    "insert_after": "si_latest_support_ticket",
                },
                {
                    "fieldname": "si_latest_support_issue_type",
                    "label": "Latest Support Issue Type",
                    "fieldtype": "Data",
                    "read_only": 1,
                    "hidden": 1,
                    "insert_after": "si_latest_support_ticket_id",
                },
                {
                    "fieldname": "si_latest_support_stage",
                    "label": "Latest Support Stage",
                    "fieldtype": "Data",
                    "read_only": 1,
                    "hidden": 1,
                    "insert_after": "si_latest_support_issue_type",
                },
                {
                    "fieldname": "si_latest_support_response",
                    "label": "Latest Support Response",
                    "fieldtype": "Small Text",
                    "read_only": 1,
                    "hidden": 1,
                    "insert_after": "si_latest_support_stage",
                },
                {
                    "fieldname": "si_latest_support_requested_on",
                    "label": "Latest Support Requested On",
                    "fieldtype": "Datetime",
                    "read_only": 1,
                    "hidden": 1,
                    "insert_after": "si_latest_support_response",
                },
            ]
        }
    )

    cleanup_duplicate_fields()


def cleanup_duplicate_fields():
    migrate_custom_field_data(DT, "si_source_encounter", "source_encounter")
    migrate_custom_field_data(DT, "si_shipkia_order_stage", "si_shipkia_stage")
    migrate_custom_field_data(DT, "shipkia_order_id", "si_shipkia_order_id")
    migrate_custom_field_data(DT, "shipkia_awb_number", "si_shipkia_awb_number")
    migrate_custom_field_data(DT, "shipkia_status", "si_shipkia_status")
    migrate_custom_field_data(DT, "shipkia_estimated_delivery", "si_shipkia_estimated_delivery")
    migrate_custom_field_data(DT, "shipkia_delivered_on", "si_shipkia_delivered_on")
    migrate_custom_field_data(DT, "shipkia_shipment", "si_shipkia_shipment")

    obsolete_fields = []
    if frappe.db.has_column(DT, "source_encounter"):
        obsolete_fields.append("si_source_encounter")
    if frappe.db.has_column(DT, "si_shipkia_stage"):
        obsolete_fields.append("si_shipkia_order_stage")

    obsolete_fields.extend(
        [
            "shipment_tracking_section",
            "shipkia_order_id",
            "shipkia_awb_number",
            "shipkia_status",
            "shipkia_estimated_delivery",
            "shipkia_delivered_on",
            "shipkia_shipment",
        ]
    )

    delete_custom_fields(DT, obsolete_fields)
