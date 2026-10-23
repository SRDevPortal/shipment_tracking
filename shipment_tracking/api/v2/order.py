"""New OMS order orchestration and stable adapter entry point."""

import sys

import frappe

from .client import send
from .payload import build_payload, money, weight_in_grams
from .responses import order_id_from_response


@frappe.whitelist(methods=["POST"])
def create_order_for_sales_invoice(invoice_name, account_name=None, force=0, replacement_reason=None):
    from shipment_tracking.api.accounts import get_account
    from shipment_tracking.services.orders import run
    default = get_account(new_order=True)
    if account_name and account_name != default.name and not int(force or 0):
        frappe.throw("New orders must use the default Shipkia account.")
    account = get_account(account_name or default.name, new_order=True)
    if account.platform != "New OMS":
        frappe.throw("V2 endpoint requires a New OMS account.")
    return run(invoice_name, account.name, sys.modules[__name__], force, replacement_reason)
