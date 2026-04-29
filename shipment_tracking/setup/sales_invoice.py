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
            ]
        }
    )

    cleanup_duplicate_fields()


def cleanup_duplicate_fields():
    migrate_custom_field_data(DT, "si_source_encounter", "source_encounter")
    migrate_custom_field_data(DT, "si_shipkia_order_stage", "si_shipkia_stage")

    obsolete_fields = []
    if frappe.db.has_column(DT, "source_encounter"):
        obsolete_fields.append("si_source_encounter")
    if frappe.db.has_column(DT, "si_shipkia_stage"):
        obsolete_fields.append("si_shipkia_order_stage")

    delete_custom_fields(DT, obsolete_fields)
