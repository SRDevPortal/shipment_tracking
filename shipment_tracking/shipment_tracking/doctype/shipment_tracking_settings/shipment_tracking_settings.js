frappe.ui.form.on("Shipment Tracking Settings", {
	setup(frm) {
		frm.set_query("default_interakt_account", () => ({
			filters: {
				channel_type: "Interakt",
				is_active: 1,
			},
		}));
	},
	refresh(frm) {
		toggle_legacy_notification_fields(frm);
	},
	whatsapp_notification_engine(frm) {
		toggle_legacy_notification_fields(frm);
	},
});

function toggle_legacy_notification_fields(frm) {
	const legacy = (frm.doc.whatsapp_notification_engine || "Legacy Shipment Tracking") === "Legacy Shipment Tracking";
	const fields = [
		"whatsapp_dry_run",
		"enable_sales_invoice_generated",
		"sales_invoice_generated_template",
		"sales_invoice_generated_language",
		"enable_order_picked_up",
		"order_picked_up_template",
		"order_picked_up_language",
		"enable_out_for_delivery",
		"out_for_delivery_template",
		"out_for_delivery_language",
		"enable_default_interakt_fallback",
		"default_interakt_account",
		"whatsapp_test_patient",
		"whatsapp_max_retries",
		"whatsapp_retry_delay_minutes",
	];
	fields.forEach((fieldname) => frm.toggle_display(fieldname, legacy));
}
