import frappe

from .utils import create_cf_with_module, delete_custom_fields, migrate_custom_field_data

DT = "Patient Encounter"
ONLINE_ONLY = 'eval:doc.sr_encounter_place=="Online"'


def apply():
    create_cf_with_module(
        {
            DT: [
                {
                    "fieldname": "pe_shipment_tracking_tab",
                    "label": "Shipment Tracking",
                    "fieldtype": "Tab Break",
                    "insert_after": "clinical_notes",
                },
                {
                    "fieldname": "pe_shipment_tracking_section",
                    "fieldtype": "Section Break",
                    "insert_after": "pe_shipment_tracking_tab",
                    "collapsible": 1,
                    "depends_on": ONLINE_ONLY,
                },
                {
                    "fieldname": "pe_shipkia_order_id",
                    "label": "Shipkia Order ID",
                    "fieldtype": "Data",
                    "read_only": 1,
                    "depends_on": ONLINE_ONLY,
                    "in_standard_filter": 1,
                    "insert_after": "pe_shipment_tracking_section",
                },
                {
                    "fieldname": "pe_shipkia_awb_number",
                    "label": "Shipkia AWB Number",
                    "fieldtype": "Data",
                    "read_only": 1,
                    "depends_on": ONLINE_ONLY,
                    "insert_after": "pe_shipkia_order_id",
                },
                {
                    "fieldname": "pe_shipkia_stage",
                    "label": "Shipkia Stage",
                    "fieldtype": "Data",
                    "read_only": 1,
                    "depends_on": ONLINE_ONLY,
                    "insert_after": "pe_shipkia_awb_number",
                },
                {
                    "fieldname": "pe_shipkia_status",
                    "label": "Shipkia Status",
                    "fieldtype": "Data",
                    "read_only": 1,
                    "depends_on": ONLINE_ONLY,
                    "in_standard_filter": 1,
                    "insert_after": "pe_shipkia_stage",
                },
                {
                    "fieldname": "pe_shipkia_estimated_delivery",
                    "label": "Estimated Delivery",
                    "fieldtype": "Datetime",
                    "read_only": 1,
                    "depends_on": ONLINE_ONLY,
                    "insert_after": "pe_shipkia_status",
                },
                {
                    "fieldname": "pe_shipkia_delivered_on",
                    "label": "Delivered On",
                    "fieldtype": "Datetime",
                    "read_only": 1,
                    "depends_on": ONLINE_ONLY,
                    "insert_after": "pe_shipkia_estimated_delivery",
                },
                {
                    "fieldname": "pe_delivery_partner",
                    "label": "Courier Partner",
                    "fieldtype": "Data",
                    "read_only": 1,
                    "depends_on": ONLINE_ONLY,
                    "insert_after": "pe_shipkia_delivered_on",
                },
                {
                    "fieldname": "pe_shipkia_shipment",
                    "label": "Shipment Record",
                    "fieldtype": "Link",
                    "options": "Shipment Tracking Shipment",
                    "read_only": 1,
                    "depends_on": ONLINE_ONLY,
                    "insert_after": "pe_delivery_partner",
                },
            ]
        }
    )

    cleanup_duplicate_fields()


def cleanup_duplicate_fields():
    migrate_custom_field_data(DT, "pe_shipkia_order_stage", "pe_shipkia_stage")

    obsolete_fields = []
    if frappe.db.has_column(DT, "pe_shipkia_stage"):
        obsolete_fields.append("pe_shipkia_order_stage")

    delete_custom_fields(DT, obsolete_fields)
