import frappe


def execute() -> None:
	if not frappe.db.get_single_value("Shipment Tracking Settings", "whatsapp_notification_engine"):
		frappe.db.set_single_value(
			"Shipment Tracking Settings",
			"whatsapp_notification_engine",
			"Legacy Shipment Tracking",
		)
