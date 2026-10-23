frappe.ui.form.on("Shipment Tracking Sync Log", {
    refresh(frm) {
        if (!frappe.user_roles.includes("System Manager") && frappe.session.user !== "Administrator") return;
        if (frm.doc.action !== "Create Order" || !["Running", "Uncertain"].includes(frm.doc.status)) return;
        frm.add_custom_button(__("Reconcile order attempt"), () => {
            frappe.prompt([
                {fieldname: "help", fieldtype: "HTML", options: "<p>Check this account in Shipkia first. This action records the verified outcome and never sends an order.</p>"},
                {fieldname: "outcome", fieldtype: "Select", label: __("Verified outcome"), options: "Created\nNot created", reqd: 1},
                {fieldname: "order_id", fieldtype: "Data", label: __("Verified order ID"), default: frm.doc.shipkia_order_id || "", depends_on: "eval:doc.outcome=='Created'", mandatory_depends_on: "eval:doc.outcome=='Created'"},
                {fieldname: "note", fieldtype: "Small Text", label: __("Evidence / reason"), reqd: 1}
            ], values => frappe.call({
                method: "shipment_tracking.api.dispatch.reconcile_order_attempt",
                args: {log_name: frm.doc.name, outcome: values.outcome, order_id: values.order_id, note: values.note},
                freeze: true,
                callback(r) { if (!r.exc) frm.reload_doc(); }
            }), __("Reconcile order attempt"), __("Save verified outcome"));
        });
    }
});
