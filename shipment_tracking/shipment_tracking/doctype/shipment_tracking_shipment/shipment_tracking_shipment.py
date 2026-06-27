import frappe
from frappe.model.document import Document


class ShipmentTrackingShipment(Document):
    def validate(self):
        if not self.shipkia_order_id:
            return

        existing = frappe.db.get_value(
            "Shipment Tracking Shipment",
            {
                "shipkia_order_id": self.shipkia_order_id,
                "name": ["!=", self.name],
            },
            "name",
        )
        if existing:
            frappe.throw(
                f"Shipkia Order ID {self.shipkia_order_id} is already linked to shipment {existing}."
            )
