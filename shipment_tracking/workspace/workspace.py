import frappe

ICON_NAME = "truck"


def create_workspace():
    if frappe.db.exists("Workspace", "Shipment Tracking"):
        doc = frappe.get_doc("Workspace", "Shipment Tracking")
    else:
        doc = frappe.new_doc("Workspace")

    doc.label = "Shipment Tracking"
    doc.title = "Shipment Tracking"
    doc.name = "Shipment Tracking"
    doc.module = "Shipment Tracking"
    doc.app = "shipment_tracking"
    doc.public = 1
    doc.is_standard = 1
    doc.icon = ICON_NAME
    doc.category = "Modules"
    doc.hide_custom = 0

    doc.set("shortcuts", [])

    doc.append("shortcuts", {
        "type": "DocType",
        "link_to": "Shipment Tracking Shipment",
        "label": "Shipments",
        "doc_view": "List",
        "color": "Blue"
    })

    doc.append("shortcuts", {
        "type": "DocType",
        "link_to": "Shipment Tracking Shipment Event",
        "label": "Shipment Events",
        "doc_view": "List",
        "color": "Purple"
    })

    doc.append("shortcuts", {
        "type": "DocType",
        "link_to": "Shipment Tracking Sync Log",
        "label": "Sync Logs",
        "doc_view": "List",
        "color": "Orange"
    })

    doc.append("shortcuts", {
        "type": "DocType",
        "link_to": "Shipment Tracking Settings",
        "label": "Settings",
        "color": "Green"
    })

    doc.set("links", [])

    doc.append("links", {
        "type": "Card Break",
        "label": "Shipment Management",
        "icon": ICON_NAME
    })

    doc.append("links", {
        "type": "Link",
        "label": "Shipments",
        "link_type": "DocType",
        "link_to": "Shipment Tracking Shipment"
    })

    doc.append("links", {
        "type": "Link",
        "label": "Shipment Events",
        "link_type": "DocType",
        "link_to": "Shipment Tracking Shipment Event"
    })

    doc.append("links", {
        "type": "Card Break",
        "label": "Logs",
        "icon": "file-text"
    })

    doc.append("links", {
        "type": "Link",
        "label": "Sync Logs",
        "link_type": "DocType",
        "link_to": "Shipment Tracking Sync Log"
    })

    doc.append("links", {
        "type": "Card Break",
        "label": "Configuration",
        "icon": "settings"
    })

    doc.append("links", {
        "type": "Link",
        "label": "Settings",
        "link_type": "DocType",
        "link_to": "Shipment Tracking Settings"
    })

    doc.save(ignore_permissions=True)
