import json

import frappe


WORKSPACE_NAME = "Shipment Tracking"
ICON_NAME = "stock"

SHORTCUTS = (
    ("Shipments", "Shipment Tracking Shipment", "List", "Blue"),
    ("Shipkia Accounts", "Shipkia Account", "List", "Green"),
    ("Sync Logs", "Shipment Tracking Sync Log", "List", "Orange"),
    ("Settings", "Shipment Tracking Settings", "", "Grey"),
)

CARDS = (
    (
        "Operations",
        "stock",
        (
            ("Shipments", "Shipment Tracking Shipment"),
            ("Support Tickets", "Shipment Tracking Support Ticket"),
        ),
    ),
    (
        "Monitoring",
        "activity",
        (
            ("Sync Logs", "Shipment Tracking Sync Log"),
            ("WhatsApp Notifications", "Shipment WhatsApp Notification"),
        ),
    ),
    (
        "Configuration",
        "settings",
        (
            ("Shipkia Accounts", "Shipkia Account"),
            ("Settings", "Shipment Tracking Settings"),
        ),
    ),
)


def create_workspace():
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
                "text": '<span class="h4"><b>Quick Access</b></span>',
                "col": 12,
            },
        },
    ]
    content.extend(
        {
            "type": "shortcut",
            "data": {"shortcut_name": label, "col": 3},
        }
        for label, _doctype, _view, _color in SHORTCUTS
    )
    content.extend(
        [
            {"type": "spacer", "data": {"col": 12}},
            {
                "type": "header",
                "data": {
                    "text": '<span class="h4"><b>Shipment Tracking</b></span>',
                    "col": 12,
                },
            },
        ]
    )
    content.extend(
        {
            "type": "card",
            "data": {"card_name": label, "col": 4},
        }
        for label, _icon, _links in CARDS
    )
    doc.content = json.dumps(content)

    doc.set("shortcuts", [])
    for label, doctype, view, color in SHORTCUTS:
        doc.append(
            "shortcuts",
            {
                "type": "DocType",
                "link_to": doctype,
                "label": label,
                "doc_view": view,
                "color": color,
            },
        )

    doc.set("links", [])
    for card_label, icon, links in CARDS:
        doc.append(
            "links",
            {
                "type": "Card Break",
                "label": card_label,
                "icon": icon,
            },
        )
        for label, doctype in links:
            doc.append(
                "links",
                {
                    "type": "Link",
                    "label": label,
                    "link_type": "DocType",
                    "link_to": doctype,
                },
            )

    doc.save(ignore_permissions=True)
