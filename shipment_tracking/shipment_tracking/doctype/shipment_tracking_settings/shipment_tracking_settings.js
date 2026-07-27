frappe.ui.form.on("Shipment Tracking Settings", {
	setup(frm) {
		frm.set_query("default_interakt_account", () => ({
			filters: {
				channel_type: "Interakt",
				is_active: 1,
			},
		}));
	},
});
