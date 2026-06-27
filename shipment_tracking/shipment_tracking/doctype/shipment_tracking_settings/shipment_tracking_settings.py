import frappe
from frappe.model.document import Document
from frappe.utils import cint


class ShipmentTrackingSettings(Document):
    def validate(self):
        if cint(self.enabled):
            self.require_value("create_order_url", "Create Order URL")
            self.require_value("pickup_address", "Pickup Address")
            self.require_value("order_channel", "Order Channel")
            self.require_password("api_key", "API Key")
            self.require_password("api_secret", "API Secret")

        if cint(self.enable_manual_tracking_refresh):
            self.require_value("tracking_url", "Tracking URL")

        if cint(self.enable_webhook_security):
            self.require_password("webhook_secret", "Webhook Secret")

        if cint(self.enable_support_ticket):
            if not cint(self.enabled):
                frappe.throw("Enable Shipment Tracking before enabling Support Ticket.")
            if not self.support_create_url and not self.has_support_url_fallback():
                frappe.throw(
                    "Support Create URL is required when Support Ticket is enabled unless a base API URL can be derived."
                )
            if not self.support_get_url and not self.has_support_url_fallback():
                frappe.throw(
                    "Support Get URL is required when Support Ticket is enabled unless a base API URL can be derived."
                )

    def require_value(self, fieldname: str, label: str):
        if not (getattr(self, fieldname, None) or "").strip():
            frappe.throw(f"{label} is required.")

    def require_password(self, fieldname: str, label: str):
        if not (self.get_password(fieldname, raise_exception=False) or "").strip():
            frappe.throw(f"{label} is required.")

    def has_support_url_fallback(self) -> bool:
        for fieldname in ("tracking_url", "create_order_url"):
            value = (getattr(self, fieldname, None) or "").strip()
            if value:
                return True
        return False

    def on_update(self):
        frappe.clear_cache()
