from .utils import create_cf_with_module


PARENT = "Sales Invoice"


def apply():
    create_cf_with_module(
        {
            PARENT: [
                {
                    "fieldname": "source_encounter",
                    "label": "Source Encounter",
                    "fieldtype": "Link",
                    "options": "Patient Encounter",
                    "read_only": 1,
                    "insert_after": "patient_name",
                },
                {
                    "fieldname": "shipment_tracking_section",
                    "label": "Shipment Tracking",
                    "fieldtype": "Section Break",
                    "insert_after": "sr_si_delivery_type",
                    "collapsible": 1,
                },
                {
                    "fieldname": "shipkia_order_id",
                    "label": "Shipkia Order ID",
                    "fieldtype": "Data",
                    "read_only": 1,
                    "in_list_view": 1,
                    "insert_after": "shipment_tracking_section",
                },
                {
                    "fieldname": "shipkia_awb_number",
                    "label": "Shipkia AWB Number",
                    "fieldtype": "Data",
                    "read_only": 1,
                    "in_list_view": 1,
                    "insert_after": "shipkia_order_id",
                },
                {
                    "fieldname": "shipkia_status",
                    "label": "Shipkia Status",
                    "fieldtype": "Data",
                    "read_only": 1,
                    "in_list_view": 1,
                    "insert_after": "shipkia_awb_number",
                },
                {
                    "fieldname": "shipkia_estimated_delivery",
                    "label": "Shipkia Estimated Delivery",
                    "fieldtype": "Datetime",
                    "read_only": 1,
                    "insert_after": "shipkia_status",
                },
                {
                    "fieldname": "shipkia_delivered_on",
                    "label": "Shipkia Delivered On",
                    "fieldtype": "Datetime",
                    "read_only": 1,
                    "insert_after": "shipkia_estimated_delivery",
                },
                {
                    "fieldname": "shipkia_shipment",
                    "label": "Shipment Record",
                    "fieldtype": "Link",
                    "options": "Shipment Tracking Shipment",
                    "read_only": 1,
                    "insert_after": "shipkia_delivered_on",
                },
            ]
        }
    )
