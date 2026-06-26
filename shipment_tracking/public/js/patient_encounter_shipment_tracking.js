(function () {
frappe.ui.form.on("Patient Encounter", {
    refresh(frm) {
        frm.remove_custom_button("Refresh Shipment Status", "Actions");

        if (has_tracking_reference(frm)) {
            add_manual_tracking_refresh_button(frm);
        }

        setTimeout(() => render_patient_encounter_support_panel(frm), 300);
    }
});

function has_tracking_reference(frm) {
    return Boolean(frm.doc.pe_shipkia_order_id || frm.doc.pe_shipkia_shipment);
}

function add_manual_tracking_refresh_button(frm) {
    frappe.call({
        method: "shipment_tracking.api.tracking.get_tracking_ui_settings",
        callback(r) {
            if (r.exc || !(r.message || {}).enable_manual_tracking_refresh) {
                return;
            }

            frm.add_custom_button(__("Refresh Shipment Status"), () => {
                frappe.call({
                    method: "shipment_tracking.api.tracking.sync_tracking_for_encounter",
                    args: { encounter_name: frm.doc.name },
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
    });
}

function render_patient_encounter_support_panel(frm) {
    if (!has_tracking_reference(frm) || !frm.fields_dict.pe_support_actions_html) {
        return;
    }

    frm.remove_custom_button("Request Reattempt", "Actions");
    frm.remove_custom_button("Request Hub Address", "Actions");
    frm.remove_custom_button("Refresh Support Ticket", "Actions");
    frm.remove_custom_button("Open Support Ticket", "Actions");
    frm.remove_custom_button("Request Reattempt", "Shipkia Support");
    frm.remove_custom_button("Request Hub Address", "Shipkia Support");
    frm.remove_custom_button("Refresh Support Ticket", "Shipkia Support");
    frm.remove_custom_button("Open Support Ticket", "Shipkia Support");

    const wrapper = frm.fields_dict.pe_support_actions_html.$wrapper;

    frappe.call({
        method: "shipment_tracking.api.support.get_support_ticket_ui_settings",
        callback(r) {
            if (r.exc || !(r.message || {}).enable_support_ticket) {
                render_existing_patient_encounter_support_panel(frm, wrapper);
                return;
            }

            wrapper.html(`<div class="text-muted small">${__("Loading support actions...")}</div>`);

            frappe.call({
                method: "shipment_tracking.api.support.get_support_state_for_encounter",
                args: { encounter_name: frm.doc.name },
                callback(r) {
                    if (!r.exc) {
                        render_support_panel({
                            frm,
                            wrapper,
                            state: r.message || {},
                            sourceArg: "encounter_name",
                            sourceName: frm.doc.name,
                            reattemptMethod: "shipment_tracking.api.support.request_reattempt_for_encounter",
                            hubMethod: "shipment_tracking.api.support.request_hub_address_for_encounter",
                            refreshTicket: frm.doc.pe_latest_support_ticket || (r.message || {}).latest_ticket
                        });
                    }
                }
            });
        }
    });
}

function render_existing_patient_encounter_support_panel(frm, wrapper) {
    frappe.call({
        method: "shipment_tracking.api.support.get_existing_support_state_for_encounter",
        args: { encounter_name: frm.doc.name },
        callback(r) {
            const state = r.message || {};
            if (r.exc || !state.has_existing_ticket) {
                wrapper.empty();
                return;
            }

            render_support_panel({
                frm,
                wrapper,
                state,
                readOnly: true,
                refreshTicket: frm.doc.pe_latest_support_ticket || state.latest_ticket
            });
        }
    });
}

function render_support_panel(config) {
    const { frm, wrapper, state, refreshTicket } = config;
    const readOnly = Boolean(config.readOnly || state.read_only);
    const latestTicket = state.latest_ticket || refreshTicket || "";
    const hubDisabled = Boolean(state.hub_address_disabled);
    const disabledText = state.hub_address_disabled_message || "";
    const responseRows = render_response_rows(
        state.responses,
        state.latest_response || frm.doc.pe_latest_support_response || ""
    );

    wrapper.html(`
        <div class="shipment-support-panel" style="display:flex; flex-direction:column; gap:10px;">
            ${readOnly ? "" : `<div class="btn-group" style="display:flex; flex-wrap:wrap; gap:8px;">
                <button class="btn btn-xs btn-primary" data-action="reattempt">${__("Request Reattempt")}</button>
                <button class="btn btn-xs btn-default" data-action="hub" ${hubDisabled ? "disabled" : ""}>
                    ${__("Request Hub Address")}
                </button>
                ${latestTicket ? `<button class="btn btn-xs btn-default" data-action="refresh">${__("Refresh Support Ticket")}</button>` : ""}
                ${latestTicket ? `<button class="btn btn-xs btn-default" data-action="open">${__("Open Support Ticket")}</button>` : ""}
            </div>`}
            ${hubDisabled ? `<div class="text-muted small">${frappe.utils.escape_html(disabledText)}</div>` : ""}
            <div class="shipment-support-chat" style="border:1px solid var(--border-color); border-radius:6px; padding:10px; background:var(--fg-color);">
                <div class="text-muted small">${__("Shipkia Response")}</div>
                <div><b>${frappe.utils.escape_html(state.latest_ticket_id || frm.doc.pe_latest_support_ticket_id || "")}</b></div>
                <div class="small">${frappe.utils.escape_html(state.latest_issue_type || frm.doc.pe_latest_support_issue_type || "")}</div>
                <div class="small">${frappe.utils.escape_html(state.latest_stage || frm.doc.pe_latest_support_stage || "")}</div>
                <div style="display:flex; flex-direction:column; gap:6px; margin-top:8px;">${responseRows}</div>
            </div>
        </div>
    `);

    if (readOnly) {
        return;
    }

    wrapper.find('[data-action="reattempt"]').on("click", () => {
        submit_support_request(config, __("Request Reattempt"), config.reattemptMethod, __("Please reattempt delivery for this shipment."));
    });
    wrapper.find('[data-action="hub"]').on("click", () => {
        if (hubDisabled) {
            frappe.msgprint(disabledText);
            return;
        }
        submit_support_request(config, __("Request Hub Address"), config.hubMethod, __("Kindly provide hub address for self pickup."));
    });
    wrapper.find('[data-action="refresh"]').on("click", () => refresh_support_ticket(frm, latestTicket));
    wrapper.find('[data-action="open"]').on("click", () => {
        frappe.set_route("Form", "Shipment Tracking Support Ticket", latestTicket);
    });
}

function render_response_rows(responses, fallback) {
    const rows = Array.isArray(responses) ? responses : [];
    if (!rows.length && fallback) {
        rows.push({ text: fallback });
    }
    if (!rows.length) {
        return `<div class="text-muted small">${__("No Shipkia response yet.")}</div>`;
    }
    return rows.map((row) => {
        const meta = [row.type, row.by, row.created_on].filter(Boolean).join(" | ");
        return `
            <div style="border-left:3px solid var(--primary); padding-left:8px;">
                ${meta ? `<div class="text-muted small">${frappe.utils.escape_html(meta)}</div>` : ""}
                <div>${frappe.utils.escape_html(row.text || "")}</div>
            </div>
        `;
    }).join("");
}

function submit_support_request(config, label, method, defaultMessage) {
    frappe.prompt(
        [{ fieldname: "message", fieldtype: "Small Text", label: __("Message"), default: defaultMessage, reqd: 1 }],
        (values) => {
            const args = {};
            args[config.sourceArg] = config.sourceName;
            args.message = values.message;
            frappe.call({
                method,
                args,
                freeze: true,
                freeze_message: __("Creating support ticket..."),
                callback(r) {
                    if (!r.exc) {
                        show_support_response(r.message);
                        config.frm.reload_doc();
                    }
                }
            });
        },
        label,
        __("Submit")
    );
}

function refresh_support_ticket(frm, ticketName) {
    frappe.call({
        method: "shipment_tracking.api.support.refresh_support_ticket",
        args: { ticket_name: ticketName },
        freeze: true,
        freeze_message: __("Refreshing support ticket..."),
        callback(r) {
            if (!r.exc) {
                show_support_response(r.message);
                frm.reload_doc();
            }
        }
    });
}

function show_support_response(data) {
    data = data || {};
    frappe.msgprint({
        title: __("Shipkia Support Response"),
        indicator: data.success ? "green" : "red",
        message: `
            <div>
                <p><b>${__("Ticket ID")}:</b> ${frappe.utils.escape_html(data.ticket_id || "")}</p>
                <p><b>${__("Stage")}:</b> ${frappe.utils.escape_html(data.stage || "")}</p>
                <p><b>${__("AWB")}:</b> ${frappe.utils.escape_html(data.awb_number || "")}</p>
                <p><b>${__("Courier")}:</b> ${frappe.utils.escape_html(data.courier_partner || "")}</p>
                <p><b>${__("Response")}:</b> ${frappe.utils.escape_html(data.latest_response || data.message || "")}</p>
            </div>
        `
    });
}
})();
