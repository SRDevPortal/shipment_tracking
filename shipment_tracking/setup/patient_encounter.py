from .utils import create_cf_with_module

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
                    "fieldname": "pe_shipkia_status",
                    "label": "Shipkia Status",
                    "fieldtype": "Data",
                    "read_only": 1,
                    "depends_on": ONLINE_ONLY,
                    "in_standard_filter": 1,
                    "insert_after": "pe_shipkia_awb_number",
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
                    "fieldname": "pe_shipkia_shipment",
                    "label": "Shipment Record",
                    "fieldtype": "Link",
                    "options": "Shipment Tracking Shipment",
                    "read_only": 1,
                    "depends_on": ONLINE_ONLY,
                    "insert_after": "pe_shipkia_delivered_on",
                },
            ]
        }
    )