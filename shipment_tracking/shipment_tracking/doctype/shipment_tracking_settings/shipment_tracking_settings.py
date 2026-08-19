import frappe
from frappe.model.document import Document
from frappe.utils import cint


class ShipmentTrackingSettings(Document):
    def validate(self):
        self.whatsapp_notification_engine = (
            getattr(self, "whatsapp_notification_engine", None) or "Legacy Shipment Tracking"
        )
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

        if self.whatsapp_notification_engine == "Patient Notification Hub":
            self.validate_patient_notification_hub()

        if (
            self.whatsapp_notification_engine == "Legacy Shipment Tracking"
            and cint(getattr(self, "enable_whatsapp_notifications", 0))
        ):
            enabled_events = (
                "enable_sales_invoice_generated",
                "enable_order_picked_up",
                "enable_out_for_delivery",
            )
            if not any(cint(getattr(self, fieldname, 0)) for fieldname in enabled_events):
                frappe.throw("Enable at least one WhatsApp notification event.")

            self.validate_whatsapp_template(
                "enable_sales_invoice_generated",
                "sales_invoice_generated_template",
                "sales_invoice_generated_language",
                "Invoice Generated",
            )
            self.validate_whatsapp_template(
                "enable_order_picked_up",
                "order_picked_up_template",
                "order_picked_up_language",
                "Order Picked Up",
            )
            self.validate_whatsapp_template(
                "enable_out_for_delivery",
                "out_for_delivery_template",
                "out_for_delivery_language",
                "Out for Delivery",
            )
            if cint(getattr(self, "whatsapp_max_retries", 0)) < 1:
                frappe.throw("Maximum Attempts must be at least 1.")
            if cint(getattr(self, "whatsapp_retry_delay_minutes", 0)) < 1:
                frappe.throw("Base Retry Delay must be at least 1 minute.")
            self.validate_default_interakt_account()

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

    def validate_whatsapp_template(
        self,
        enable_field: str,
        template_field: str,
        language_field: str,
        label: str,
    ) -> None:
        if not cint(getattr(self, enable_field, 0)):
            return
        self.require_value(template_field, f"{label} Template")
        self.require_value(language_field, f"{label} Language")

    def validate_default_interakt_account(self) -> None:
        if not cint(getattr(self, "enable_default_interakt_fallback", 0)):
            return
        self.require_value("default_interakt_account", "Default Interakt Account")
        account = frappe.get_doc("Chat Channel Account", self.default_interakt_account)
        if not cint(account.is_active):
            frappe.throw("Default Interakt Account must be active.")
        if account.channel_type != "Interakt":
            frappe.throw("Default Interakt Account must use the Interakt channel type.")
        if not (account.get_password("interakt_api_key", raise_exception=False) or "").strip():
            frappe.throw("Default Interakt Account must have an Interakt API Key.")

    def validate_patient_notification_hub(self) -> None:
        if "patient_notification_hub" not in frappe.get_installed_apps():
            frappe.throw("Install Patient Notification Hub before selecting it as the notification engine.")
        if not frappe.db.exists("DocType", "Patient Notification Settings"):
            frappe.throw("Patient Notification Hub settings are not available. Run bench migrate and try again.")
        if not cint(frappe.db.get_single_value("Patient Notification Settings", "enabled")):
            frappe.throw("Enable Patient Notification Hub before switching the notification engine.")
        required_rules = {"sales_invoice_generated", "order_picked_up", "out_for_delivery"}
        enabled_rules = {
            row.rule_key
            for row in frappe.get_all(
                "Patient Notification Rule",
                filters={"rule_key": ["in", sorted(required_rules)], "enabled": 1},
                fields=["rule_key"],
                limit_start=0,
                limit_page_length=len(required_rules),
            )
        }
        missing = sorted(required_rules - enabled_rules)
        if missing:
            frappe.msgprint(
                "Patient Notification Hub is selected, but these rules are disabled: " + ", ".join(missing),
                indicator="orange",
                alert=True,
            )

    def on_update(self):
        frappe.clear_cache()
