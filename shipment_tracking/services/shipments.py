"""Provider-neutral local shipment persistence; no provider HTTP calls."""
import hashlib
import frappe

from shipment_tracking.services.statuses import update_doc_if_exists


def identity_key(account, order_id):
    return hashlib.sha256((account + "\0" + order_id).encode()).hexdigest()


def save_order_shipment(invoice, account, order_id, body, replaces=None, reason=None):
    matches = frappe.get_all("Shipment Tracking Shipment", filters={"shipkia_account": account.name, "shipkia_order_id": order_id}, pluck="name", limit=2)
    if matches:
        frappe.throw("Returned order ID already exists for this account. Reconcile the sync log.")
    encounter = get_linked_encounter(invoice)
    shipment = frappe.get_doc({
        "doctype": "Shipment Tracking Shipment", "shipkia_account": account.name,
        "shipkia_order_id": order_id, "external_identity_key": identity_key(account.name, order_id),
        "sales_invoice": invoice.name, "patient_encounter": encounter.name if encounter else None,
        "patient": getattr(invoice, "patient", None), "customer": invoice.customer,
        "replaces_shipment": replaces, "replacement_reason": reason,
        "raw_latest_response": frappe.as_json(body),
    }).insert(ignore_permissions=True)
    values = {"si_shipkia_order_id": order_id, "si_shipkia_shipment": shipment.name,
              "si_shipkia_awb_number": None, "si_delivery_partner": None, "si_courier_partner_mode": None,
              "si_shipkia_stage": None, "si_shipkia_status": None,
              "si_shipkia_estimated_delivery": None, "si_shipkia_delivered_on": None}
    for suffix in ("latest_support_ticket", "latest_support_ticket_id", "latest_support_issue_type",
                   "latest_support_stage", "latest_support_response", "latest_support_requested_on"):
        values["si_" + suffix] = None
    frappe.db.set_value("Sales Invoice", invoice.name, values, update_modified=False)
    if encounter:
        frappe.db.set_value("Patient Encounter", encounter.name,
                            {k.replace("si_", "pe_", 1): v for k, v in values.items()}, update_modified=False)
    return shipment


def mirror_summary_fields(shipment, sales_invoice: str | None, encounter_name: str | None):

    # Sales Invoice fields
    si_values = {
        "si_shipkia_order_id": shipment.shipkia_order_id,
        "si_shipkia_awb_number": shipment.shipkia_awb_number,
        "si_delivery_partner": shipment.delivery_partner,
        "si_courier_partner_mode": shipment.courier_partner_mode,
        "si_shipkia_stage": shipment.shipkia_stage,
        "si_shipkia_status": shipment.shipkia_status,
        "si_shipkia_estimated_delivery": shipment.shipkia_estimated_delivery,
        "si_shipkia_delivered_on": shipment.shipkia_delivered_on,
        "si_shipkia_shipment": shipment.name,
    }

    # Patient Encounter fields
    pe_values = {
        "pe_shipkia_order_id": shipment.shipkia_order_id,
        "pe_shipkia_awb_number": shipment.shipkia_awb_number,
        "pe_delivery_partner": shipment.delivery_partner,
        "pe_courier_partner_mode": shipment.courier_partner_mode,
        "pe_shipkia_stage": shipment.shipkia_stage,
        "pe_shipkia_status": shipment.shipkia_status,
        "pe_shipkia_estimated_delivery": shipment.shipkia_estimated_delivery,
        "pe_shipkia_delivered_on": shipment.shipkia_delivered_on,
        "pe_shipkia_shipment": shipment.name,
    }

    current = frappe.db.get_value("Sales Invoice", sales_invoice, "si_shipkia_shipment") if sales_invoice else None
    if not current or current == shipment.name:
        update_doc_if_exists("Sales Invoice", sales_invoice, si_values)
    current = frappe.db.get_value("Patient Encounter", encounter_name, "pe_shipkia_shipment") if encounter_name else None
    if not current or current == shipment.name:
        update_doc_if_exists("Patient Encounter", encounter_name, pe_values)


def get_linked_encounter(si):
    for fieldname in ("source_encounter", "patient_encounter", "sr_patient_encounter", "reference_name"):
        value = getattr(si, fieldname, None)
        if value and frappe.db.exists("Patient Encounter", value):
            return frappe.get_doc("Patient Encounter", value)

    remarks = getattr(si, "remarks", "") or ""
    marker = "Patient Encounter:"
    if marker in remarks:
        parts = remarks.split(marker, 1)[1].strip().split()
        candidate = parts[0] if parts else ""
        if candidate and frappe.db.exists("Patient Encounter", candidate):
            return frappe.get_doc("Patient Encounter", candidate)

    if not getattr(si, "patient", None):
        return None
    encounter_name = frappe.db.get_value(
        "Patient Encounter",
        {"patient": getattr(si, "patient", None), "docstatus": 1},
        "name",
        order_by="modified desc",
    )
    if encounter_name:
        return frappe.get_doc("Patient Encounter", encounter_name)
    return None

