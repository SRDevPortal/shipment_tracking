import json

import frappe
from frappe.utils import cint


WORKSPACE_NAME = "Shipment Tracking"
ICON_NAME = "stock"


def is_support_ticket_enabled():
    try:
        if not frappe.db.exists("DocType", "Shipment Tracking Settings"):
            return False
        settings = frappe.get_single("Shipment Tracking Settings")
        return bool(cint(getattr(settings, "enabled", 0)) and cint(getattr(settings, "enable_support_ticket", 0)))
    except Exception:
        return False


def create_workspace():
    support_ticket_enabled = is_support_ticket_enabled()

    if frappe.db.exists("Workspace", WORKSPACE_NAME):
        doc = frappe.get_doc("Workspace", WORKSPACE_NAME)
    else:
        doc = frappe.new_doc("Workspace")

    doc.name = WORKSPACE_NAME
    doc.label = WORKSPACE_NAME
    doc.title = WORKSPACE_NAME
    doc.module = "Shipment Tracking"
    doc.app = "shipment_tracking"
    doc.public = 1
    doc.is_standard = 1
    doc.icon = ICON_NAME
    doc.category = "Modules"
    doc.sequence_id = 998
    doc.hide_custom = 0
    content = [
        {
            "type": "header",
            "data": {
                "text": '<span class="h4"><b>Shipment Tracking</b></span>',
                "col": 12,
            },
        },
        {
            "type": "shortcut",
            "data": {
                "shortcut_name": "Shipments",
                "col": 3,
            },
        },
    ]
    if support_ticket_enabled:
        content.append(
            {
                "type": "shortcut",
                "data": {
                    "shortcut_name": "Support Tickets",
                    "col": 3,
                },
            }
        )
    content.extend(
        [
            {
                "type": "shortcut",
                "data": {
                    "shortcut_name": "Sync Logs",
                    "col": 3,
                },
            },
            {
                "type": "shortcut",
                "data": {
                    "shortcut_name": "Settings",
                    "col": 3,
                },
            },
        ]
    )
    doc.content = json.dumps(content)

    doc.set("shortcuts", [])

    doc.append("shortcuts", {
        "type": "DocType",
        "link_to": "Shipment Tracking Shipment",
        "label": "Shipments",
        "doc_view": "List",
        "color": "Blue"
    })

    if support_ticket_enabled:
        doc.append("shortcuts", {
            "type": "DocType",
            "link_to": "Shipment Tracking Support Ticket",
            "label": "Support Tickets",
            "doc_view": "List",
            "color": "Red"
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

    if support_ticket_enabled:
        doc.append("links", {
            "type": "Link",
            "label": "Support Tickets",
            "link_type": "DocType",
            "link_to": "Shipment Tracking Support Ticket"
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
