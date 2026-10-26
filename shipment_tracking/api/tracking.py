"""Public manual-tracking endpoints and platform router."""
from __future__ import annotations

import frappe
from frappe.utils import cint

from shipment_tracking.api.accounts import LEGACY_ACCOUNT, get_account, legacy_settings
from shipment_tracking.services.shipments import get_linked_encounter, mirror_summary_fields
from shipment_tracking.services.statuses import ACTIVE_SYNC_DEFAULT_LIMIT, TERMINAL_STATUSES


def _account_for_shipment(shipment):
    if not shipment.shipkia_account:
        frappe.throw("Shipment account is unassigned. Ask an administrator to review ownership.")
    return get_account(shipment.shipkia_account)

def _tracking_account_for_shipment(shipment):
    if not shipment.shipkia_account:
        frappe.throw("Shipment account is unassigned. Ask an administrator to review ownership.")

    settings = frappe.get_single("Shipment Tracking Settings")
    if settings.default_shipkia_account:
        gateway_account = get_account(settings.default_shipkia_account)
        if gateway_account.platform == "New OMS":
            return gateway_account

    # Sites that have not switched to New OMS retain historic per-account routing.
    return _account_for_shipment(shipment)


def _adapter_for(account):
    if account.platform == "Legacy":
        from shipment_tracking.api import legacy_tracking as adapter
    elif account.platform == "New OMS":
        from shipment_tracking.api.v2 import tracking as adapter
    else:
        frappe.throw("Unsupported Shipkia platform.")
    return adapter


def _find_reference_shipment(reference, link_field, relation_field, order_field):
    linked_name = getattr(reference, link_field, None)
    if linked_name:
        shipment = frappe.get_doc("Shipment Tracking Shipment", linked_name)
        if shipment.get(relation_field) and shipment.get(relation_field) != reference.name:
            frappe.throw("The linked shipment belongs to another document.")
        return shipment

    candidates = frappe.get_all(
        "Shipment Tracking Shipment",
        filters={relation_field: reference.name},
        pluck="name",
        limit=2,
    )
    order_id = getattr(reference, order_field, None)
    if not candidates and order_id:
        candidates = frappe.get_all(
            "Shipment Tracking Shipment",
            filters={"shipkia_order_id": order_id},
            pluck="name",
            limit=2,
        )
    if len(candidates) > 1:
        frappe.throw("Multiple shipments match. Open the specific shipment for review.")
    return frappe.get_doc("Shipment Tracking Shipment", candidates[0]) if candidates else None


def _tracking_identifier_available(shipment, platform):
    if platform == "Legacy":
        return bool(shipment.shipkia_order_id)
    if platform == "New OMS":
        return bool(shipment.shipkia_order_id)
    return False


def _validate_tracking_enabled(account):
    if not cint(account.allow_existing_operations):
        frappe.throw("Existing operations are disabled for this Shipkia account.")
    if not cint(account.enable_manual_tracking_refresh):
        frappe.throw("Tracking is disabled for this Shipkia account.")
    if not account.order_tracking_url:
        frappe.throw("Configure the Order Tracking URL for this Shipkia account.")


def _sync_tracking(shipment):
    account = _tracking_account_for_shipment(shipment)
    _validate_tracking_enabled(account)
    from shipment_tracking.services.tracking import run
    return run(shipment, account, _adapter_for(account))


@frappe.whitelist()
def get_tracking_ui_settings(invoice_name=None, encounter_name=None):
    if invoice_name or encounter_name:
        is_invoice = bool(invoice_name)
        reference = frappe.get_doc(
            "Sales Invoice" if is_invoice else "Patient Encounter",
            invoice_name or encounter_name,
        )
        reference.check_permission("read")
        shipment = _find_reference_shipment(
            reference,
            "si_shipkia_shipment" if is_invoice else "pe_shipkia_shipment",
            "sales_invoice" if is_invoice else "patient_encounter",
            "si_shipkia_order_id" if is_invoice else "pe_shipkia_order_id",
        )
        if not shipment:
            return {"enable_manual_tracking_refresh": False}
        account = _tracking_account_for_shipment(shipment)
        configured = bool(
            account.allow_existing_operations
            and account.enable_manual_tracking_refresh
            and account.order_tracking_url
        )
        identifier_available = _tracking_identifier_available(
            shipment,
            account.platform,
        )
        return {
            "enable_manual_tracking_refresh": configured and identifier_available,
            "tracking_configured": configured,
            "tracking_available": identifier_available,
            "unavailable_reason": (
                None
                if identifier_available
                else "Shipkia has not assigned a tracking ID or AWB yet."
            ),
            "account": account.name,
            "platform": account.platform,
            "shipment_account": shipment.shipkia_account,
            "shipment": shipment.name,
            "order_id": shipment.shipkia_order_id,
            "tracking_id": shipment.shipkia_tracking_id,
            "awb": shipment.shipkia_awb_number,
            "stage": shipment.shipkia_stage,
            "status": shipment.shipkia_status,
            "courier": shipment.delivery_partner,
            "courier_mode": shipment.courier_partner_mode,
            "last_updated": shipment.last_synced_on,
        }

    account = legacy_settings()
    return {
        "enable_manual_tracking_refresh": bool(account.enable_manual_tracking_refresh),
        "account": account.name,
        "platform": account.platform,
    }


@frappe.whitelist(methods=["POST"])
def sync_tracking_for_shipment(shipment_name):
    shipment = frappe.get_doc("Shipment Tracking Shipment", shipment_name)
    shipment.check_permission("read")
    shipment.check_permission("write")
    return _sync_tracking(shipment)


@frappe.whitelist(methods=["POST"])
def sync_tracking_for_invoice(invoice_name):
    invoice = frappe.get_doc("Sales Invoice", invoice_name)
    invoice.check_permission("read")
    invoice.check_permission("write")
    shipment = _find_reference_shipment(
        invoice,
        "si_shipkia_shipment",
        "sales_invoice",
        "si_shipkia_order_id",
    )
    if not shipment:
        frappe.throw("No shipment record linked to this Sales Invoice.")
    repair_shipment_links(
        shipment,
        si=invoice,
        order_id=getattr(invoice, "si_shipkia_order_id", None),
    )
    return _sync_tracking(shipment)


@frappe.whitelist(methods=["POST"])
def sync_tracking_for_encounter(encounter_name):
    encounter = frappe.get_doc("Patient Encounter", encounter_name)
    encounter.check_permission("read")
    encounter.check_permission("write")
    shipment = _find_reference_shipment(
        encounter,
        "pe_shipkia_shipment",
        "patient_encounter",
        "pe_shipkia_order_id",
    )
    if not shipment:
        frappe.throw("No shipment record linked to this Patient Encounter.")
    repair_shipment_links(
        shipment,
        encounter=encounter,
        order_id=getattr(encounter, "pe_shipkia_order_id", None),
    )
    return _sync_tracking(shipment)


@frappe.whitelist(methods=["POST"])
def sync_tracking_by_order_id(order_id):
    names = frappe.get_all(
        "Shipment Tracking Shipment",
        filters={"shipkia_order_id": order_id},
        pluck="name",
        limit=2,
    )
    if len(names) != 1:
        frappe.throw("Order ownership is missing or ambiguous. Open the specific shipment instead.")
    shipment = frappe.get_doc("Shipment Tracking Shipment", names[0])
    shipment.check_permission("read")
    shipment.check_permission("write")
    return _sync_tracking(shipment)


def validate_manual_tracking_refresh_enabled(account=None):
    account = account or legacy_settings()
    _validate_tracking_enabled(account)


def get_or_create_shipment(si=None, encounter=None, order_id=None, create=True):
    order_id = (order_id or "").strip()
    lookups = []
    if order_id:
        lookups.append({"shipkia_order_id": order_id, "shipkia_account": LEGACY_ACCOUNT})
    if si:
        lookups.extend([
            {"name": getattr(si, "si_shipkia_shipment", None)},
            {"sales_invoice": si.name},
        ])
    if encounter:
        lookups.extend([
            {"name": getattr(encounter, "pe_shipkia_shipment", None)},
            {"patient_encounter": encounter.name},
        ])

    seen = set()
    for filters in lookups:
        filters = {key: value for key, value in filters.items() if value}
        if not filters:
            continue
        filters["shipkia_account"] = LEGACY_ACCOUNT
        key = tuple(sorted(filters.items()))
        if key in seen:
            continue
        seen.add(key)
        names = frappe.get_all(
            "Shipment Tracking Shipment",
            filters=filters,
            pluck="name",
            limit=2,
        )
        if len(names) > 1:
            frappe.throw("Multiple Legacy shipments match. Open the specific shipment for review.")
        if names:
            return frappe.get_doc("Shipment Tracking Shipment", names[0])
    if not create:
        return None
    return frappe.get_doc({
        "doctype": "Shipment Tracking Shipment",
        "shipkia_account": LEGACY_ACCOUNT,
    })


def repair_shipment_links(shipment, si=None, encounter=None, order_id=None):
    changed = False
    if si:
        if shipment.sales_invoice and shipment.sales_invoice != si.name:
            frappe.throw(
                f"Shipment {shipment.name} is already linked to Sales Invoice {shipment.sales_invoice}."
            )
        if not shipment.sales_invoice:
            shipment.sales_invoice = si.name
            changed = True
        if getattr(si, "patient", None) and shipment.patient != si.patient:
            shipment.patient = si.patient
            changed = True
        if getattr(si, "customer", None) and shipment.customer != si.customer:
            shipment.customer = si.customer
            changed = True

    if encounter and shipment.patient_encounter and shipment.patient_encounter != encounter.name:
        frappe.throw(
            f"Shipment {shipment.name} is already linked to Patient Encounter {shipment.patient_encounter}."
        )
    if encounter and not shipment.patient_encounter:
        shipment.patient_encounter = encounter.name
        changed = True
    if encounter and getattr(encounter, "patient", None) and shipment.patient != encounter.patient:
        shipment.patient = encounter.patient
        changed = True

    if order_id and shipment.shipkia_order_id and shipment.shipkia_order_id != order_id:
        frappe.throw("Cannot overwrite a shipment order ID. Create a replacement shipment.")
    if order_id and shipment.shipkia_order_id != order_id:
        shipment.shipkia_order_id = order_id
        changed = True

    if changed and not shipment.is_new():
        shipment.save(ignore_permissions=True)
        mirror_summary_fields(
            shipment,
            sales_invoice=shipment.sales_invoice,
            encounter_name=shipment.patient_encounter,
        )
    return changed


def create_or_update_shipment_from_order_response(si, encounter, order_id, body):
    shipment = get_or_create_shipment(
        si=si,
        encounter=encounter,
        order_id=order_id,
    )
    repair_shipment_links(
        shipment,
        si=si,
        encounter=encounter,
        order_id=order_id,
    )
    shipment.raw_latest_response = frappe.as_json(body)
    if shipment.is_new():
        shipment.insert(ignore_permissions=True)
    else:
        shipment.save(ignore_permissions=True)
    mirror_summary_fields(
        shipment,
        sales_invoice=si.name,
        encounter_name=encounter.name if encounter else None,
    )
    return shipment


def apply_tracking_response(shipment, body):
    from shipment_tracking.api import legacy_tracking
    from shipment_tracking.services.tracking import apply_tracking_data
    data = legacy_tracking.parse_response(body, shipment)
    return apply_tracking_data(shipment, data, body)


def sync_timeline(shipment, timeline_rows):
    from shipment_tracking.services.tracking import sync_timeline as shared_sync_timeline
    changed = shared_sync_timeline(shipment, timeline_rows)
    if changed:
        shipment.save(ignore_permissions=True)
    return changed


def sync_active_shipments():
    names = frappe.get_all(
        "Shipment Tracking Shipment",
        filters={"normalized_status": ["not in", list(TERMINAL_STATUSES)]},
        pluck="name",
        limit=ACTIVE_SYNC_DEFAULT_LIMIT,
    )
    for name in names:
        try:
            shipment = frappe.get_doc("Shipment Tracking Shipment", name)
            account = _tracking_account_for_shipment(shipment)
            if account.enable_manual_tracking_refresh and account.allow_existing_operations:
                _sync_tracking(shipment)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"Shipment Tracking auto-sync failed for {name}",
            )


def _check_tracking_for_reference(reference, is_invoice):
    shipment = _find_reference_shipment(
        reference,
        "si_shipkia_shipment" if is_invoice else "pe_shipkia_shipment",
        "sales_invoice" if is_invoice else "patient_encounter",
        "si_shipkia_order_id" if is_invoice else "pe_shipkia_order_id",
    )
    if not shipment:
        frappe.throw("No shipment record is linked to this document.")
    shipment.check_permission("read")
    account = _tracking_account_for_shipment(shipment)
    _validate_tracking_enabled(account)
    from shipment_tracking.services.tracking import check_for_updates
    return check_for_updates(shipment, account, _adapter_for(account))


@frappe.whitelist(methods=["POST"])
def check_tracking_for_invoice(invoice_name):
    invoice = frappe.get_doc("Sales Invoice", invoice_name)
    invoice.check_permission("read")
    return _check_tracking_for_reference(invoice, True)


@frappe.whitelist(methods=["POST"])
def check_tracking_for_encounter(encounter_name):
    encounter = frappe.get_doc("Patient Encounter", encounter_name)
    encounter.check_permission("read")
    return _check_tracking_for_reference(encounter, False)


@frappe.whitelist(methods=["POST"])
def apply_tracking_check(check_token):
    from shipment_tracking.services.tracking import apply_checked_update
    return apply_checked_update(check_token)
