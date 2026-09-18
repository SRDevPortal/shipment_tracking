"""Summary-only shipping support responses for restricted pilot viewers."""
import frappe


def support_summary(data):
    if not frappe.conf.get("privacy_shield_desk_enabled", False):
        return data
    from privacy_shield.policy import current_capabilities
    if current_capabilities().view_full:
        return data
    # Preserve local navigation and booleans, never provider prose/IDs or attachments.
    keys = ("success", "read_only", "has_existing_ticket", "ticket", "latest_ticket",
            "latest_requested_on", "hub_address_disabled", "hub_address_disabled_until")
    result = {key: data[key] for key in keys if key in data}
    result.update(latest_response="", responses=[], details_restricted=True)
    result["message"] = "Support status updated. Reply details require full-number visibility."
    return result


def restricted_support():
    if not frappe.conf.get("privacy_shield_desk_enabled", False):
        return False
    from privacy_shield.policy import current_capabilities
    return not current_capabilities().view_full


def linked_support_summary(reference, ticket_name=None):
    """Read only summary metadata after authorizing the source and its binding.

    Does not relax raw document permission or fetch provider reply fields.
    """
    links = {"Sales Invoice": "sales_invoice", "Patient Encounter": "patient_encounter"}
    if reference.doctype not in links:
        raise frappe.PermissionError("Unsupported support summary source")
    reference.check_permission("read")
    prefix = "si" if reference.doctype == "Sales Invoice" else "pe"
    order_id = reference.get(prefix + "_shipkia_order_id")
    user = frappe.session.user
    manager = user == "Administrator" or "System Manager" in frappe.get_roles(user)
    fields = ["name", "owner", "creation", "shipkia_order_id", links[reference.doctype]]
    filters = {"name": ticket_name} if ticket_name else {"shipkia_order_id": order_id}
    if not ticket_name and not order_id:
        return support_summary({"success": True, "read_only": True, "has_existing_ticket": False})
    if not manager:
        filters["owner"] = user
    ticket = frappe.db.get_value("Shipment Tracking Support Ticket", filters, fields,
                                 as_dict=True, order_by="creation desc")
    if ticket_name and not ticket:
        raise frappe.PermissionError("Support summary is unavailable for this reference")
    if ticket:
        linked_source = ticket.get(links[reference.doctype])
        # A conflicting stored source must never be accepted just because order IDs match.
        if linked_source:
            matches = linked_source == reference.name
        else:
            matches = bool(order_id and ticket.shipkia_order_id == order_id)
        if not matches:
            raise frappe.PermissionError("Support summary is unavailable for this reference")
    return support_summary({
        "success": True, "read_only": True, "has_existing_ticket": bool(ticket),
        "latest_ticket": ticket.name if ticket else "",
        "latest_requested_on": ticket.creation if ticket else None,
    })
