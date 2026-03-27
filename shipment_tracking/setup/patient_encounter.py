from .utils import create_cf_with_module


DT = "Patient Encounter"
ONLINE_ONLY = 'eval:doc.sr_encounter_place=="Online"'


def apply():
    create_cf_with_module(
        {
            DT: [
                {
                    "fieldname": "shipment_tracking_section",
                    "label": "Shipment Tracking",
                    "fieldtype": "Section Break",
                    "insert_after": "sr_encounter_status",
                    "collapsible": 1,
                    "depends_on": ONLINE_ONLY,
                },
                {
                    "fieldname": "shipkia_order_id",
                    "label": "Shipkia Order ID",
                    "fieldtype": "Data",
                    "read_only": 1,
                    "depends_on": ONLINE_ONLY,
                    "insert_after": "shipment_tracking_section",
                },
                {
                    "fieldname": "shipkia_awb_number",
                    "label": "Shipkia AWB Number",
                    "fieldtype": "Data",
                    "read_only": 1,
                    "depends_on": ONLINE_ONLY,
                    "insert_after": "shipkia_order_id",
                },
                {
                    "fieldname": "shipkia_status",
                    "label": "Shipkia Status",
                    "fieldtype": "Data",
                    "read_only": 1,
                    "depends_on": ONLINE_ONLY,
                    "insert_after": "shipkia_awb_number",
                },
                {
                    "fieldname": "shipkia_estimated_delivery",
                    "label": "Shipkia Estimated Delivery",
                    "fieldtype": "Datetime",
                    "read_only": 1,
                    "depends_on": ONLINE_ONLY,
                    "insert_after": "shipkia_status",
                },
                {
                    "fieldname": "shipkia_delivered_on",
                    "label": "Shipkia Delivered On",
                    "fieldtype": "Datetime",
                    "read_only": 1,
                    "depends_on": ONLINE_ONLY,
                    "insert_after": "shipkia_estimated_delivery",
                },
                {
                    "fieldname": "shipkia_shipment",
                    "label": "Shipment Record",
                    "fieldtype": "Link",
                    "options": "Shipment Tracking Shipment",
                    "read_only": 1,
                    "depends_on": ONLINE_ONLY,
                    "insert_after": "shipkia_delivered_on",
                },
            ]
        }
    )
