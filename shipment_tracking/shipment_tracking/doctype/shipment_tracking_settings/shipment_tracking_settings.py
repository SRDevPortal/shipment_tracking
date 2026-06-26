import frappe
from frappe.model.document import Document
from frappe.utils import cint


class ShipmentTrackingSettings(Document):
    def validate(self):
        if cint(self.enable_manual_tracking_refresh):
            if not self.tracking_url:
                frappe.throw("Tracking URL is required when Manual Tracking Refresh is enabled.")
            return

        self.tracking_url = ""

    def on_update(self):
        try:
            from shipment_tracking.workspace import create_workspace

            create_workspace()
            frappe.clear_cache()
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Shipment Tracking Workspace Refresh Failed")
