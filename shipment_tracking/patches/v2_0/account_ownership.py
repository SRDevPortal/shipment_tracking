"""Idempotent configuration migration. Never sends provider requests or edits history payloads."""
import frappe
from shipment_tracking.services.shipments import identity_key


def execute():
    settings = frappe.get_single("Shipment Tracking Settings")
    existed = frappe.db.exists("Shipkia Account", "Legacy")
    if not existed:
        account = frappe.get_doc({"doctype": "Shipkia Account", "name": "Legacy", "platform": "Legacy",
                                  "allow_new_orders": 1, "allow_existing_operations": 1})
    else:
        account = frappe.get_doc("Shipkia Account", "Legacy")
    # Existing account migration marker is authoritative. Do not overwrite operator edits.
    if not account.get("legacy_configuration_migrated"):
        for field in ("create_order_url", "pickup_address", "order_channel",
                      "default_parcel_length", "default_parcel_breadth", "default_parcel_height",
                      "default_dead_weight", "enable_manual_tracking_refresh", "enable_webhook_security",
                      "enable_support_ticket", "support_create_url", "support_update_url", "support_get_url", "support_list_url"):
            if not existed or account.get(field) in (None, ""):
                account.set(field, settings.get(field))
        if not existed or account.get("order_tracking_url") in (None, ""):
            account.order_tracking_url = settings.get("tracking_url")
        for field in ("api_key", "api_secret", "webhook_secret"):
            if not existed or not account.get_password(field, raise_exception=False):
                secret = settings.get_password(field, raise_exception=False)
                if secret:
                    account.set(field, secret)
        account.legacy_configuration_migrated = 1
        if existed:
            account.save(ignore_permissions=True)
        else:
            account.insert(ignore_permissions=True)
    if not settings.default_shipkia_account:
        frappe.db.set_single_value("Shipment Tracking Settings", "default_shipkia_account", "Legacy")
    frappe.db.set_single_value("Shipment Tracking Settings", "legacy_configuration_migrated", 1)
    # A database upgraded directly from Legacy has no account-labelled rows. Existing mixed
    # deployments require explicit ownership evidence; leave unknown ownership for review.
    any_assigned = frappe.db.sql("select name from `tabShipment Tracking Shipment` where coalesce(shipkia_account, '') != '' limit 1")
    if not any_assigned and not frappe.db.exists("Shipkia Account", {"platform": "New OMS"}):
        for dt in ("Shipment Tracking Shipment", "Shipment Tracking Sync Log", "Shipment Tracking Support Ticket"):
            frappe.db.sql("update `tab" + dt + "` set shipkia_account='Legacy' where coalesce(shipkia_account,'')=''")
    # Derive unassigned logs/tickets only from an unambiguous linked shipment/reference.
    for dt, link in (("Shipment Tracking Support Ticket", "shipment"),):
        frappe.db.sql("update `tab" + dt + "` t join `tabShipment Tracking Shipment` s on s.name=t." + link + " set t.shipkia_account=s.shipkia_account where coalesce(t.shipkia_account,'')='' and coalesce(s.shipkia_account,'')!=''")
    frappe.db.sql("""update `tabShipment Tracking Sync Log` l join `tabShipment Tracking Shipment` s
        on l.reference_doctype='Shipment Tracking Shipment' and l.reference_name=s.name
        set l.shipkia_account=s.shipkia_account where coalesce(l.shipkia_account,'')=''
        and coalesce(s.shipkia_account,'')!=''""")
    # Historical duplicate identities stay intact and receive no unique hash.
    rows = frappe.db.sql("""select shipkia_account, shipkia_order_id, min(name) name
        from `tabShipment Tracking Shipment` where coalesce(shipkia_account,'')!=''
        and coalesce(shipkia_order_id,'')!='' group by shipkia_account,shipkia_order_id having count(*)=1 and sum(coalesce(external_identity_key,'')='')>0""", as_dict=True)
    for row in rows:
        frappe.db.sql("update `tabShipment Tracking Shipment` set external_identity_key=%s where name=%s and coalesce(external_identity_key,'')=''",
                      (identity_key(row.shipkia_account, row.shipkia_order_id), row.name))
