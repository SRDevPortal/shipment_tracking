(function () {
frappe.ui.form.on("Sales Invoice", {
    refresh(frm) {
        if (frm.doc.docstatus !== 1) {
            return;
        }

        frm.remove_custom_button("Send to Shipkia2", "Actions");
        frm.remove_custom_button("Resend to Shipkia2", "Actions");
        frm.remove_custom_button("Refresh Shipment Status", "Actions");
        frm.remove_custom_button("Open Shipment", "Actions");
        frm.remove_custom_button("Request Reattempt", "Actions");
        frm.remove_custom_button("Request Hub Address", "Actions");
        frm.remove_custom_button("Refresh Support Ticket", "Actions");
        frm.remove_custom_button("Open Support Ticket", "Actions");

        const shipkia_order_id = frm.doc.si_shipkia_order_id;
        frm.add_custom_button(__(shipkia_order_id ? "Create Replacement Shipkia Order" : "Create Shipkia Order"), () => {
            frappe.call({
                method: "shipment_tracking.api.dispatch.get_order_context",
                args: {invoice_name: frm.doc.name},
                callback(r) {
                    if (r.exc || !r.message) return;
                    const context = r.message;
                    const send = (reason, dialog) => frappe.call({
                        method: "shipment_tracking.api.dispatch.create_order_for_sales_invoice",
                        args: {
                            invoice_name: frm.doc.name,
                            force: shipkia_order_id ? 1 : 0,
                            replacement_reason: reason || "",
                            confirmed_account: context.account,
                            ui_mode: 1
                        },
                        freeze: true,
                        freeze_message: __("Creating Shipkia order..."),
                        callback(result) {
                            if (!result.exc && result.message) {
                                if (dialog) dialog.hide();
                                show_order_result(frm, result.message);
                            }
                        },
                        always() {
                            if (dialog) dialog.get_primary_btn().prop("disabled", false);
                        }
                    });
                    if (shipkia_order_id) {
                        frappe.prompt([
                            {fieldname: "summary", fieldtype: "HTML", options: order_confirmation_html(context, true)},
                            {fieldname: "reason", fieldtype: "Small Text", label: __("Replacement reason"), reqd: 1}
                        ], (values) => send(values.reason), __("Create replacement order"), __("Create order"));
                    } else {
                        show_order_confirmation(context, (dialog) => send("", dialog));
                    }
                }
            });
        }, __("Actions"));

        if (has_tracking_reference(frm)) {
            add_manual_tracking_refresh_button(frm);
        }

        setTimeout(() => render_sales_invoice_support_panel(frm), 300);
    }
});

function order_confirmation_html(context, replacement = false) {
    const currency = context.currency;
    const outstanding = Number(context.outstanding || 0);
    const paid = Number(context.paid || 0);
    const rows = [
        [__("Account"), frappe.utils.escape_html(context.account)],
        [__("Payment"), frappe.utils.escape_html(context.payment)],
        [__("Invoice total"), format_currency(context.invoice_total, currency)]
    ];
    if (paid > 0) {
        rows.push([__(outstanding > 0 ? "Already paid" : "Amount paid"), format_currency(paid, currency)]);
    }
    rows.push([__("Amount to collect"), format_currency(Math.max(outstanding, 0), currency), "shipment-collect-amount"]);

    const summary = rows.map(([label, value, className]) => `
        <div style="display:grid;grid-template-columns:42% 58%;padding:10px 14px;border-bottom:1px solid var(--border-color);">
            <span class="text-muted">${label}</span>
            <strong class="${className || ""}">${value}</strong>
        </div>`).join("");
    const note = replacement
        ? __("The old shipment and its history will be preserved.")
        : __("The default Shipkia account will be used.");
    return `
        <div style="margin-bottom:14px;color:var(--text-muted);">${__("Send this invoice to Shipkia?")}</div>
        <div style="border:1px solid var(--border-color);border-radius:8px;overflow:hidden;">${summary}</div>
        <div class="text-muted small" style="margin-top:10px;">${note}</div>
        <style>.shipment-collect-amount{color:var(--primary);font-size:1.08em;}</style>`;
}

function show_order_confirmation(context, on_confirm) {
    const dialog = new frappe.ui.Dialog({
        title: __("Create Shipkia Order"),
        fields: [{fieldname: "summary", fieldtype: "HTML"}],
        primary_action_label: __("Create Order"),
        secondary_action_label: __("Cancel"),
        secondary_action() {
            dialog.hide();
        },
        primary_action() {
            dialog.get_primary_btn().prop("disabled", true);
            on_confirm(dialog);
        }
    });
    dialog.fields_dict.summary.$wrapper.html(order_confirmation_html(context));
    dialog.show();
}

function order_result_rows(result) {
    const rows = [];
    const add = (label, value) => {
        if (!value) return;
        rows.push(`
            <div style="display:grid;grid-template-columns:42% 58%;padding:10px 14px;border-bottom:1px solid var(--border-color);">
                <span class="text-muted">${__(label)}</span>
                <strong>${frappe.utils.escape_html(String(value))}</strong>
            </div>`);
    };
    add("Shipkia Order", result.order_id);
    return rows.join("");
}
function order_failure_guidance(result) {
    const outcome = result.outcome || "local_validation_failed";
    const message = String(result.message || "").toLowerCase();
    if (outcome === "uncertain") {
        return __("Do not retry. Check Shipkia and reconcile the existing attempt.");
    }
    if (outcome === "local_save_failed") {
        return __("Do not resend. Shipkia created the order and ERPNext requires reconciliation.");
    }
    if (message.includes("api key") || message.includes("unauthorized") || message.includes("authentication")) {
        return __("Check the API key configured for New OMS. No Shipkia order was created. You can retry after correcting the configuration.");
    }
    if (message.includes("postal") || message.includes("pincode")) {
        return __("Correct the delivery postal code, then try again. No Shipkia order was created.");
    }
    if (message.includes("phone") || message.includes("mobile")) {
        return __("Add a valid customer mobile number, then try again. No Shipkia order was created.");
    }
    if (message.includes("pickup")) {
        return __("Check the pickup address configured for this Shipkia account. No Shipkia order was created.");
    }
    return result.request_sent
        ? __("No Shipkia order was created. Correct the issue before retrying.")
        : __("No request was sent to Shipkia. Correct the issue and try again.");
}


function order_result_html(result) {
    const outcome = result.outcome || "local_validation_failed";
    if (outcome === "created") {
        const details = order_result_rows(result);
        return `
            <div style="border:1px solid var(--border-color);border-radius:8px;overflow:hidden;margin-bottom:12px;">${details}</div>
            <div style="padding:10px 12px;border-radius:8px;background:var(--subtle-fg);">
                ${frappe.utils.escape_html(String(result.message || __("Order created successfully")))}
            </div>`;
    }
    const colors = {
        created: "var(--green-700)",
        local_validation_failed: "var(--blue-500)",
        provider_rejected: "var(--red-500)",
        uncertain: "var(--orange-500)",
        local_save_failed: "var(--orange-500)"
    };
    const guidance = order_failure_guidance(result);
    const validations = (result.validation_messages || [])
        .filter(Boolean)
        .map((message) => `<li style="margin:5px 0;">${frappe.utils.escape_html(String(message))}</li>`)
        .join("");
    const details = order_result_rows(result);
    return `
        ${details ? `<div style="border:1px solid var(--border-color);border-radius:8px;overflow:hidden;margin-bottom:12px;">${details}</div>` : ""}
        <div style="padding:10px 12px;border-radius:8px;background:var(--subtle-fg);">
            ${frappe.utils.escape_html(String(result.message || __("No additional details were provided.")))}
        </div>
        ${validations ? `<ul style="margin:10px 0 0;padding-left:22px;">${validations}</ul>` : ""}
        <div style="display:flex;align-items:flex-start;gap:8px;margin-top:12px;color:${colors[outcome] || "var(--text-muted)"};">
            <span style="font-size:16px;">&#9679;</span>
            <span>${frappe.utils.escape_html(guidance)}</span>
        </div>`;
}

function show_order_result(frm, result) {
    const dialog = new frappe.ui.Dialog({
        title: __(result.outcome === "provider_rejected" ? "Unable to Create Shipkia Order" : (result.title || (result.success ? "Shipkia Order Created" : "Order Could Not Be Created"))),
        fields: [{fieldname: "summary", fieldtype: "HTML"}],
        primary_action_label: __(result.success ? "Done" : "Close"),
        primary_action() {
            dialog.hide();
            if (result.success) {
                frm.reload_doc();
            }
        }
    });
    dialog.fields_dict.summary.$wrapper.html(order_result_html(result));
    dialog.show();
}

function has_tracking_reference(frm) {
    return Boolean(frm.doc.si_shipkia_order_id || frm.doc.si_shipkia_shipment);
}

function add_manual_tracking_refresh_button(frm) {
    frappe.call({
        method: "shipment_tracking.api.tracking.get_tracking_ui_settings",
        args: {invoice_name: frm.doc.name},
        callback(r) {
            const context = r.message || {};
            if (r.exc || !context.enable_manual_tracking_refresh) return;

            frm.add_custom_button(__("Refresh Shipment Status"), () => {
                frappe.call({
                    method: "shipment_tracking.api.tracking.check_tracking_for_invoice",
                    args: {invoice_name: frm.doc.name},
                    freeze: true,
                    freeze_message: __("Checking latest status from Shipkia..."),
                    callback(result) {
                        if (!result.exc && result.message) {
                            show_tracking_check(frm, result.message);
                        }
                    }
                });
            }, __("Actions"));
        }
    });
}


function tracking_display_date(value) {
    if (!value || value === "-") return "-";
    try {
        return frappe.datetime.str_to_user(value);
    } catch (e) {
        return String(value);
    }
}

function tracking_summary_rows(rows) {
    return rows.map(([label, value, valueHtml]) => `
        <div style="display:grid;grid-template-columns:42% 58%;padding:10px 14px;border-bottom:1px solid var(--border-color);">
            <span class="text-muted">${__(label)}</span>
            <strong>${valueHtml || frappe.utils.escape_html(String(value || "-"))}</strong>
        </div>`).join("");
}

function tracking_summary_html(summary, note, noteColor = "var(--green-700)") {
    const status = frappe.utils.escape_html(summary.status || summary.stage || __("Not available"));
    const statusBadge = `<span style="display:inline-flex;align-items:center;gap:6px;padding:3px 9px;border-radius:12px;background:var(--green-100);color:var(--green-700);"><span>&#9679;</span>${status}</span>`;
    const rows = tracking_summary_rows([
        ["Shipkia Order", summary.order_id],
        ["AWB", summary.awb || "Not assigned"],
        ["Stage", summary.stage || "Not available"],
        ["Status", summary.status || summary.stage, statusBadge],
        ["Courier", summary.courier || "Not assigned"],
        ["Mode", summary.courier_mode || "-"],
        ["Last Updated", tracking_display_date(summary.last_updated)]
    ]);
    return `
        <div style="border:1px solid var(--border-color);border-radius:8px;overflow:hidden;">${rows}</div>
        <div style="display:flex;align-items:center;gap:8px;margin-top:12px;color:${noteColor};">
            <span style="font-size:16px;">&#9679;</span>
            <span>${__(note)}</span>
        </div>`;
}

function tracking_changes_html(check) {
    const identity = tracking_summary_rows([
        ["Shipkia Order", check.summary.order_id],
        ["AWB", check.summary.awb || "Not assigned"]
    ]);
    const changeRows = (check.changes || []).map((row) => `
        <tr>
            <td style="padding:9px 12px;border:1px solid var(--border-color);">${frappe.utils.escape_html(__(row.label))}</td>
            <td style="padding:9px 12px;border:1px solid var(--border-color);">${frappe.utils.escape_html(row.field === "status_time" ? tracking_display_date(row.erpnext) : String(row.erpnext || "-"))}</td>
            <td style="padding:9px 12px;border:1px solid var(--border-color);font-weight:600;">${frappe.utils.escape_html(row.field === "status_time" ? tracking_display_date(row.shipkia) : String(row.shipkia || "-"))}</td>
        </tr>`).join("");
    const identityNote = check.identity_changed && !changeRows
        ? `<div class="text-muted small" style="margin-top:10px;">${__("Shipment identifiers will be synchronized.")}</div>`
        : "";
    return `
        <div style="margin-bottom:12px;color:var(--text-muted);">${__("Shipkia has newer tracking information.")}</div>
        <div style="border:1px solid var(--border-color);border-radius:8px;overflow:hidden;">${identity}</div>
        <div style="font-weight:600;margin:14px 0 8px;">${__("Changes")}</div>
        ${changeRows ? `<table style="width:100%;border-collapse:collapse;">
            <thead><tr style="background:var(--subtle-fg);">
                <th style="padding:9px 12px;border:1px solid var(--border-color);text-align:left;">${__("Field")}</th>
                <th style="padding:9px 12px;border:1px solid var(--border-color);text-align:left;">ERPNext</th>
                <th style="padding:9px 12px;border:1px solid var(--border-color);text-align:left;">Shipkia</th>
            </tr></thead>
            <tbody>${changeRows}</tbody>
        </table>` : ""}
        ${identityNote}
        <div style="display:flex;align-items:center;gap:8px;margin-top:12px;color:var(--blue-500);">
            <span style="font-size:16px;">&#9679;</span>
            <span>${__("Review the changes before updating ERPNext.")}</span>
        </div>`;
}

function show_tracking_check(frm, check) {
    if (!check.update_available) {
        const dialog = new frappe.ui.Dialog({
            title: __("Shipment Already Up to Date"),
            fields: [{fieldname: "summary", fieldtype: "HTML"}],
            primary_action_label: __("Done"),
            primary_action() {
                dialog.hide();
            }
        });
        dialog.fields_dict.summary.$wrapper.html(tracking_summary_html(
            check.summary,
            check.provider_older
                ? "ERPNext already contains newer shipment information."
                : "No newer tracking update was found."
        ));
        dialog.show();
        return;
    }

    const dialog = new frappe.ui.Dialog({
        title: __("Shipment Update Available"),
        fields: [{fieldname: "summary", fieldtype: "HTML"}],
        primary_action_label: __("Refresh Status"),
        secondary_action_label: __("Cancel"),
        secondary_action() {
            dialog.hide();
        },
        primary_action() {
            dialog.get_primary_btn().prop("disabled", true);
            frappe.call({
                method: "shipment_tracking.api.tracking.apply_tracking_check",
                args: {check_token: check.check_token},
                freeze: true,
                freeze_message: __("Updating shipment status..."),
                callback(r) {
                    if (!r.exc && r.message) {
                        dialog.hide();
                        const applied = r.message;
                        const resultDialog = new frappe.ui.Dialog({
                            title: __(applied.updated ? "Shipment Status Updated" : "Shipment Already Up to Date"),
                            fields: [{fieldname: "summary", fieldtype: "HTML"}],
                            primary_action_label: __("Done"),
                            primary_action() {
                                resultDialog.hide();
                            }
                        });
                        resultDialog.fields_dict.summary.$wrapper.html(tracking_summary_html(
                            applied,
                            applied.updated
                                ? "Tracking details were saved to ERPNext."
                                : "No newer tracking update was found."
                        ));
                        resultDialog.show();
                        frm.reload_doc();
                    }
                },
                always() {
                    dialog.get_primary_btn().prop("disabled", false);
                }
            });
        }
    });
    dialog.fields_dict.summary.$wrapper.html(tracking_changes_html(check));
    dialog.show();
}

function render_sales_invoice_support_panel(frm) {
    if (!frm.doc.si_shipkia_order_id || !frm.fields_dict.si_support_actions_html) {
        return;
    }

    const wrapper = frm.fields_dict.si_support_actions_html.$wrapper;

    frappe.call({
        method: "shipment_tracking.api.support.get_support_ticket_ui_settings",
        args: {invoice_name: frm.doc.name},
        callback(r) {
            if (r.exc || !(r.message || {}).enable_support_ticket) {
                render_existing_sales_invoice_support_panel(frm, wrapper);
                return;
            }

            wrapper.html(`<div class="text-muted small">${__("Loading support actions...")}</div>`);

            frappe.call({
                method: "shipment_tracking.api.support.get_support_state_for_invoice",
                args: { invoice_name: frm.doc.name },
                callback(r) {
                    if (!r.exc) {
                        render_support_panel({
                            frm,
                            wrapper,
                            state: r.message || {},
                            sourceArg: "invoice_name",
                            sourceName: frm.doc.name,
                            reattemptMethod: "shipment_tracking.api.support.request_reattempt_for_invoice",
                            hubMethod: "shipment_tracking.api.support.request_hub_address_for_invoice",
                            refreshTicket: frm.doc.si_latest_support_ticket || (r.message || {}).latest_ticket
                        });
                    }
                }
            });
        }
    });
}

function render_existing_sales_invoice_support_panel(frm, wrapper) {
    frappe.call({
        method: "shipment_tracking.api.support.get_existing_support_state_for_invoice",
        args: { invoice_name: frm.doc.name },
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
                refreshTicket: frm.doc.si_latest_support_ticket || state.latest_ticket
            });
        }
    });
}

function render_support_panel(config) {
    const { frm, wrapper, state, refreshTicket } = config;
    if (state.details_restricted) {
        wrapper.html(`<div class="shipment-support-panel privacy-support-summary">
            <div class="text-muted small">${__("Shipment support")}</div>
            <div>${__("Reply details are hidden by your privacy permissions.")}</div>
        </div>`);
        return;
    }
    const readOnly = Boolean(config.readOnly || state.read_only);
    const latestTicket = state.latest_ticket || refreshTicket || "";
    const hubDisabled = Boolean(state.hub_address_disabled);
    const disabledText = state.hub_address_disabled_message || "";
    const responseRows = render_response_rows(
        state.responses,
        state.latest_response || frm.doc.si_latest_support_response || ""
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
                <div><b>${frappe.utils.escape_html(state.latest_ticket_id || frm.doc.si_latest_support_ticket_id || "")}</b></div>
                <div class="small">${frappe.utils.escape_html(state.latest_issue_type || frm.doc.si_latest_support_issue_type || "")}</div>
                <div class="small">${frappe.utils.escape_html(state.latest_stage || frm.doc.si_latest_support_stage || "")}</div>
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
