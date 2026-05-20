frappe.ui.form.on("Sales Invoice", {
    refresh(frm) {
        if (frm.doc.docstatus !== 1) {
            return;
        }

        frm.remove_custom_button("Send to Shipkia2", "Actions");
        frm.remove_custom_button("Resend to Shipkia2", "Actions");
        frm.remove_custom_button("Refresh Shipment Status", "Actions");
        frm.remove_custom_button("Open Shipment", "Actions");

        const shipkia_order_id = frm.doc.si_shipkia_order_id;
        const shipkia_shipment = frm.doc.si_shipkia_shipment;
        const can_open_shipment = frappe.session.user === "Administrator"
            || frappe.user_roles.includes("System Manager");

        if (!shipkia_order_id) {
            frm.add_custom_button(__("Create Shipkia Order"), () => {
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
            frm.add_custom_button(__("Recreate Shipkia Order"), () => {
                frappe.confirm("This Sales Invoice already has a Shipkia order. Recreate it anyway?", () => {
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
            if (can_open_shipment) {
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
        }

        if (shipkia_shipment && can_open_shipment) {
            frm.add_custom_button(__("Open Shipment"), () => {
                frappe.set_route("Form", "Shipment Tracking Shipment", shipkia_shipment);
            }, __("Actions"));
        }
    }
});
