import frappe
from frappe.model.document import Document
from urllib.parse import urlsplit
from frappe.utils import cint, cstr

class ShipkiaAccount(Document):
    def validate(self):
        if not self.is_new():
            old = self.get_doc_before_save()
            if old and old.platform != self.platform:
                frappe.throw("Account platform cannot be changed. Create a separate account.")
        self.validate_optional_features()
        self.validate_v2_parcel_defaults()
        for field in ("api_base_url", "create_order_url", "order_details_url", "order_tracking_url", "support_create_url", "support_update_url", "support_get_url", "support_list_url"):
            value = self.get(field)
            if value and (urlsplit(value).scheme != "https" or not urlsplit(value).netloc):
                frappe.throw('API URLs must use HTTPS.')

    def validate_v2_parcel_defaults(self):
        if self.platform != "New OMS":
            return
        for field in ("default_parcel_length", "default_parcel_breadth", "default_parcel_height"):
            value = self.get(field)
            if value not in (None, "") and value < 10:
                frappe.throw(f"{self.meta.get_label(field)} must be at least 10 cm for New OMS.")
        if self.default_dead_weight not in (None, "") and self.default_dead_weight <= 0:
            frappe.throw("Default Dead Weight must be greater than 0 grams for New OMS.")

    def validate_optional_features(self):
        tracking_required = (
            ("order_details_url", "order_tracking_url")
            if self.platform == "New OMS"
            else ("order_tracking_url",)
        )
        features = (
            (
                "enable_manual_tracking_refresh",
                tracking_required,
                ("order_details_url", "order_tracking_url"),
            ),
            ("enable_webhook_security", ("webhook_secret",), ("webhook_secret",)),
            ("enable_support_ticket", ("support_create_url", "support_get_url"),
             ("support_create_url", "support_update_url", "support_get_url", "support_list_url")),
        )
        for toggle, required, fields in features:
            if not cint(self.get(toggle)):
                for field in fields:
                    self.set(field, None)
                continue
            for field in required:
                value = self.get_password(field, raise_exception=False) if field == "webhook_secret" else self.get(field)
                if not cstr(value).strip():
                    label = self.meta.get_label(field)
                    frappe.throw(f"{label} is required when {self.meta.get_label(toggle)} is enabled.")
