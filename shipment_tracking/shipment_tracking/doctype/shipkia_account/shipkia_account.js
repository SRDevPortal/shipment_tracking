frappe.ui.form.on("Shipkia Account", {
    enable_manual_tracking_refresh(frm) {
        return clear_disabled_shipkia_fields(frm, "enable_manual_tracking_refresh", ["order_details_url", "order_tracking_url"]);
    },
    enable_webhook_security(frm) {
        return clear_disabled_shipkia_fields(frm, "enable_webhook_security", ["webhook_secret"]);
    },
    enable_support_ticket(frm) {
        return clear_disabled_shipkia_fields(frm, "enable_support_ticket", [
            "support_create_url", "support_update_url", "support_get_url", "support_list_url"
        ]);
    },
    refresh(frm) {
        const v2 = frm.doc.platform === "New OMS";
        frm.toggle_display(["v2_contract_verified", "v2_order_id_path", "api_base_url"], v2);
        if (v2) frm.dashboard.set_headline_alert("V2 order, tracking and webhook adapters are active. Support remains unavailable until its API contract is verified.", "blue");
        frm.set_df_property("platform", "read_only", !frm.is_new());

    }
});
function clear_disabled_shipkia_fields(frm, toggle, fields) {
    if (frm.doc[toggle]) return;
    return frm.set_value(Object.fromEntries(fields.map(field => [field, ""])));
}
