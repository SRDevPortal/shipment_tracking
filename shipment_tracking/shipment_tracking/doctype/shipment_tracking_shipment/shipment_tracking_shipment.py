import frappe
from frappe.model.document import Document
from shipment_tracking.services.shipments import identity_key


class ShipmentTrackingShipment(Document):
    def validate(self):
        if not self.shipkia_order_id:
            return
        old = self.get_doc_before_save() if not self.is_new() else None
        if old and old.shipkia_order_id == self.shipkia_order_id and old.shipkia_account == self.shipkia_account:
            return  # Preserve historical duplicate identities during unrelated status updates.
        if old and (old.shipkia_order_id != self.shipkia_order_id or old.shipkia_account != self.shipkia_account):
            frappe.throw("Shipment order ID and account cannot be changed. Create a replacement shipment.")
        if not self.shipkia_account:
            frappe.throw("Shipment account is required.")
        if frappe.db.exists("Shipment Tracking Shipment", {"shipkia_account": self.shipkia_account,
            "shipkia_order_id": self.shipkia_order_id, "name": ["!=", self.name]}):
            frappe.throw("This account already has a shipment with that order ID.")
        self.external_identity_key = identity_key(self.shipkia_account, self.shipkia_order_id)
