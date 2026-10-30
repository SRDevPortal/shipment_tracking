"""Durable operation journal and invoice lock, shared by independent adapters."""
import frappe
from frappe.utils import cint
from shipment_tracking.api.accounts import get_account, reference_account
from shipment_tracking.services.order_results import provider_summary, result
from shipment_tracking.services.shipments import save_order_shipment


def run(invoice_name, account_name, adapter, force=0, replacement_reason=None, ui_mode=0):
    # Lock spans journaling, network call and commit. Running is durable before POST.
    with frappe.cache().lock("shipkia:create:" + invoice_name, timeout=180, blocking_timeout=2):
        invoice = frappe.get_doc("Sales Invoice", invoice_name)
        invoice.check_permission("read")
        invoice.check_permission("write")
        if invoice.docstatus != 1:
            frappe.throw("Sales Invoice must be submitted.")
        account = get_account(account_name, new_order=True)
        pending = frappe.db.exists("Shipment Tracking Sync Log", {
            "reference_doctype": "Sales Invoice", "reference_name": invoice_name,
            "action": "Create Order", "status": ["in", ["Running", "Uncertain"]]})
        if pending:
            frappe.throw("An earlier order attempt requires reconciliation. No order was sent.")
        old = getattr(invoice, "si_shipkia_shipment", None)
        if getattr(invoice, "si_shipkia_order_id", None):
            if not cint(force):
                frappe.throw("This invoice already has a Shipkia order.")
            if not old:
                frappe.throw("Link the existing shipment before creating a replacement.")
            previous = frappe.get_doc("Shipment Tracking Shipment", old)
            if reference_account(previous) != account.name:
                frappe.throw("A replacement must use the original shipment account.")
            if not (replacement_reason or "").strip():
                frappe.throw("Enter a reason for creating a replacement order.")
        else:
            old = None
        payload = adapter.build_payload(invoice, account)
        log = frappe.get_doc({"doctype": "Shipment Tracking Sync Log", "direction": "Outbound",
            "action": "Create Order", "reference_doctype": "Sales Invoice", "reference_name": invoice.name,
            "shipkia_account": account.name, "replaces_shipment": old,
            "replacement_reason": replacement_reason, "status": "Running",
            # Patient/address data is deliberately excluded from the operation journal.
            "request_json": frappe.as_json({"invoice": invoice.name, "account": account.name,
                                           "item_count": len(payload.get("product_details", []))})
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        try:
            response, body, order_id = adapter.send(account, payload)
            log.http_status = response.status_code
            log.response_json = frappe.as_json(body)
            if response.status_code in (200, 201, 202) and not order_id:
                raise ValueError("Successful response did not contain the configured order ID")
        except Exception:
            log.status = "Uncertain"
            log.error_message = "No confirmed order ID. Check Shipkia before resolving this attempt."
            log.save(ignore_permissions=True)
            frappe.db.commit()
            if cint(ui_mode):
                return result(
                    "uncertain", "Order Outcome Requires Review",
                    "Shipkia may have received this request. Check Shipkia before retrying.",
                    request_sent=True, account=account.name, sync_log=log.name,
                )
            frappe.throw("Order outcome is uncertain. Check Shipkia before retrying; automatic retry is blocked.")
        if response.status_code not in (200, 201, 202):
            log.status = "Failed" if response.status_code in (400, 401, 403, 404, 422) else "Uncertain"
            log.error_message = "Provider rejected order" if log.status == "Failed" else "Provider outcome is uncertain"
            log.save(ignore_permissions=True)
            frappe.db.commit()
            if cint(ui_mode):
                summary = provider_summary(
                    body,
                    "Shipkia rejected the order." if log.status == "Failed"
                    else "Shipkia may have received this request. Check Shipkia before retrying.",
                )
                return result(
                    "provider_rejected" if log.status == "Failed" else "uncertain",
                    "Shipkia Rejected the Order" if log.status == "Failed"
                    else "Order Outcome Requires Review",
                    summary["message"], request_sent=True,
                    retry_allowed=log.status == "Failed", account=account.name,
                    sync_log=log.name,
                    validation_messages=summary["validation_messages"],
                    provider_trace_id=summary["provider_trace_id"],
                )
            frappe.throw("Order was not confirmed. Review the sync log before retrying.")
        try:
            shipment = save_order_shipment(invoice, account, str(order_id), body, old, replacement_reason)
            log.status = "Success"
            log.shipkia_order_id = str(order_id)
            log.save(ignore_permissions=True)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            log = frappe.get_doc("Shipment Tracking Sync Log", log.name)
            log.status = "Uncertain"
            log.shipkia_order_id = str(order_id)
            log.response_json = frappe.as_json(body)
            log.http_status = response.status_code
            log.error_message = "Provider created an order but local persistence failed. Reconcile; do not resend."
            log.save(ignore_permissions=True)
            frappe.db.commit()
            if cint(ui_mode):
                return result(
                    "local_save_failed", "Order Created - ERPNext Review Required",
                    "Shipkia created the order, but ERPNext could not save the local shipment. Do not resend.",
                    request_sent=True, account=account.name, order_id=str(order_id),
                    sync_log=log.name,
                )
            raise
        summary = provider_summary(body, "Order created successfully.")
        provider_result = body.get("result") if isinstance(body, dict) else None
        provider_status = provider_result.get("status") if isinstance(provider_result, dict) else None
        if cint(ui_mode):
            return result(
                "created", "Shipkia Order Created", summary["message"],
                success=True, request_sent=True, account=account.name,
                order_id=str(order_id), shipment=shipment.name, sync_log=log.name,
                provider_status=provider_status,
                provider_trace_id=summary["provider_trace_id"],
            )
        return {"success": True, "order_id": str(order_id), "shipment": shipment.name,
                "account": account.name, "message": "Shipkia order created: " + str(order_id)}
