import frappe
from frappe.utils import cint, flt
from .accounts import get_account, reference_account
from shipment_tracking.services.order_results import local_validation


@frappe.whitelist(methods=["POST"])
def create_order_for_sales_invoice(
    invoice_name,
    force=0,
    replacement_reason=None,
    confirmed_account=None,
    ui_mode=0,
):
    try:
        invoice = frappe.get_doc("Sales Invoice", invoice_name)
        invoice.check_permission("read")
        invoice.check_permission("write")
        name = None
        if cint(force) and getattr(invoice, "si_shipkia_shipment", None):
            name = reference_account(
                frappe.get_doc("Shipment Tracking Shipment", invoice.si_shipkia_shipment)
            )
        account = get_account(name, new_order=True)
        if confirmed_account and confirmed_account != account.name:
            frappe.throw("The selected account has changed. Confirm the order again.")
        from shipment_tracking.services.orders import run
        if account.platform == "Legacy":
            from . import order as adapter
        elif account.platform == "New OMS":
            from .v2 import order as adapter
        else:
            frappe.throw("Unsupported Shipkia platform.")
        return run(
            invoice_name, account.name, adapter, force, replacement_reason,
            ui_mode=ui_mode,
        )
    except frappe.ValidationError as exc:
        if cint(ui_mode):
            frappe.clear_messages()
            return local_validation(str(exc))
        raise


@frappe.whitelist()
def get_order_context(invoice_name):
    invoice = frappe.get_doc("Sales Invoice", invoice_name)
    invoice.check_permission("read")
    invoice.check_permission("write")
    name = None
    if getattr(invoice, "si_shipkia_shipment", None):
        name = reference_account(frappe.get_doc("Shipment Tracking Shipment", invoice.si_shipkia_shipment))
    account = get_account(name, new_order=True)
    total = flt(invoice.grand_total)
    outstanding = flt(invoice.outstanding_amount)
    paid = max(total - outstanding, 0)
    if outstanding <= 0:
        payment = "Prepaid"
    elif paid > 0:
        payment = "Partial Payment + COD"
    else:
        payment = "Cash on Delivery"
    return {"account": account.name, "platform": account.platform, "payment": payment,
            "invoice_total": total, "paid": paid, "outstanding": outstanding,
            "currency": invoice.currency}


@frappe.whitelist(methods=["POST"])
def reconcile_order_attempt(log_name, outcome, note, order_id=None):
    """Explicit administrator reconciliation; never submits another provider order."""
    frappe.only_for("System Manager")
    if not (note or "").strip():
        frappe.throw("A reconciliation note is required.")
    log = frappe.get_doc("Shipment Tracking Sync Log", log_name)
    log.check_permission("write")
    if log.action != "Create Order" or log.reference_doctype != "Sales Invoice":
        frappe.throw("Select a Create Order attempt.")
    with frappe.cache().lock("shipkia:create:" + log.reference_name, timeout=180, blocking_timeout=2):
        log.reload()
        if log.status not in ("Running", "Uncertain"):
            frappe.throw("This attempt does not need reconciliation.")
        if outcome == "Not created":
            log.status = "Resolved"
        elif outcome == "Created":
            if not (order_id or log.shipkia_order_id):
                frappe.throw("Enter the verified Shipkia order ID.")
            invoice = frappe.get_doc("Sales Invoice", log.reference_name)
            invoice.check_permission("write")
            if invoice.si_shipkia_shipment != log.replaces_shipment and invoice.si_shipkia_shipment:
                frappe.throw("The invoice shipment has changed. Review before linking this order.")
            account = frappe.get_doc("Shipkia Account", log.shipkia_account)
            from shipment_tracking.services.shipments import save_order_shipment
            save_order_shipment(invoice, account, str(order_id or log.shipkia_order_id),
                                {"reconciled": True, "log": log.name}, log.replaces_shipment, log.replacement_reason)
            log.shipkia_order_id = str(order_id or log.shipkia_order_id)
            log.status = "Success"
        else:
            frappe.throw("Choose Created or Not created after checking Shipkia.")
        log.reconciliation_note = note
        log.add_comment("Info", "Reconciled by " + frappe.session.user + ": " + note)
        log.save(ignore_permissions=True)
        frappe.db.commit()
        return {"success": True, "status": log.status}
