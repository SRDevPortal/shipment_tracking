frappe.ui.form.on("Sales Invoice", {
    refresh(frm) {
        if (frm.doc.docstatus !== 1) {
            return;
        }

        if (!frm.doc.shipkia_order_id) {
            frm.add_custom_button(__("Send to Shipkia2"), () => {
                frappe.confirm("Create Shipkia order for this Sales Invoice?", () => {
                    frappe.call({
                        method: "shipment_tracking.api.order.create_order_for_sales_invoice",
                        args: { invoice_name: frm.doc.name },
                        freeze: true,
                        freeze_message: __("Creating Shipkia order..."),
                        callback(r) {
                            if (!r.exc) {
                                frappe.msgprint(r.message.message || "Shipkia order created.");
                                frm.reload_doc();
                            }
                        }
                    });
                });
            }, __("Actions"));
        } else {
            frm.add_custom_button(__("Resend to Shipkia2"), () => {
                frappe.confirm("This invoice already has a Shipkia order. Create again anyway?", () => {
                    frappe.call({
                        method: "shipment_tracking.api.order.create_order_for_sales_invoice",
                        args: { invoice_name: frm.doc.name, force: 1 },
                        freeze: true,
                        freeze_message: __("Recreating Shipkia order..."),
                        callback(r) {
                            if (!r.exc) {
                                frappe.msgprint(r.message.message || "Shipkia order recreated.");
                                frm.reload_doc();
                            }
                        }
                    });
                });
            }, __("Actions"));
            frm.add_custom_button(__("Refresh Shipment Status"), () => {
                frappe.call({
                    method: "shipment_tracking.api.tracking.sync_tracking_for_invoice",
                    args: { invoice_name: frm.doc.name },
                    freeze: true,
                    freeze_message: __("Refreshing shipment status..."),
                    callback(r) {
                        if (!r.exc) {
                            frappe.msgprint(r.message.message || "Shipment updated.");
                            frm.reload_doc();
                        }
                    }
                });
            }, __("Actions"));
        }

        if (frm.doc.shipkia_shipment) {
            frm.add_custom_button(__("Open Shipment"), () => {
                frappe.set_route("Form", "Shipment Tracking Shipment", frm.doc.shipkia_shipment);
            }, __("Actions"));
        }
    }
});
