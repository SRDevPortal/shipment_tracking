"""Account selection. Historic operations never follow the current default."""
import frappe
from frappe.utils import cint

LEGACY_ACCOUNT = "Legacy"

def reference_account(reference):
    account = getattr(reference, "shipkia_account", None)
    if account:
        return account
    for field, doctype in (("si_shipkia_shipment", "Shipment Tracking Shipment"), ("pe_shipkia_shipment", "Shipment Tracking Shipment"), ("shipment", "Shipment Tracking Shipment")):
        name = getattr(reference, field, None)
        if name:
            account = frappe.db.get_value(doctype, name, "shipkia_account")
            if account:
                return account
    # Unassigned historic references require migration/review, never default routing.
    frappe.throw("Shipment account is unassigned. Ask an administrator to review ownership.")

def get_account(name=None, new_order=False):
    settings = frappe.get_single("Shipment Tracking Settings")
    if not settings.enabled:
        frappe.throw("Shipment Tracking is disabled.")
    name = name or (settings.default_shipkia_account if new_order else LEGACY_ACCOUNT)
    if not name:
        frappe.throw("Choose the default Shipkia Account in Shipment Tracking Settings.")
    account = frappe.get_doc("Shipkia Account", name)
    flag = "allow_new_orders" if new_order else "allow_existing_operations"
    if not cint(account.get(flag)):
        frappe.throw("This Shipkia Account does not allow this operation.")
    return account

def legacy_settings(reference=None, new_order=False):
    account = get_account(reference_account(reference) if reference else LEGACY_ACCOUNT, new_order=new_order)
    if account.platform != "Legacy":
        frappe.throw("This operation is unavailable for V2. Legacy APIs cannot operate on V2 shipments.")
    account.enabled = 1
    return account
