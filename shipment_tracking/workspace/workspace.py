import frappe


def create_workspace():
    if frappe.db.exists("Workspace", "Shipment Tracking"):
        doc = frappe.get_doc("Workspace", "Shipment Tracking")
    else:
        doc = frappe.new_doc("Workspace")

    # -------------------------------
    # Basic Info
    # -------------------------------
    doc.label = "Shipment Tracking"
    doc.title = "Shipment Tracking"
    doc.name = "Shipment Tracking"
    doc.module = "Shipment Tracking"
    doc.app = "shipment_tracking"
    doc.public = 1
    doc.is_standard = 1
    doc.icon = "shipment-truck"   # ✅ workspace icon
    doc.category = "Modules"
    doc.hide_custom = 0

    # -------------------------------
    # Shortcuts (Top Cards)
    # -------------------------------
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

    # ✅ Single DocType (NO doc_view)
    doc.append("shortcuts", {
        "type": "DocType",
        "link_to": "Shipment Tracking Settings",
        "label": "Settings",
        "color": "Green"
    })

    # -------------------------------
    # Sidebar Links (Left Menu)
    # -------------------------------
    doc.set("links", [])

    # 🚚 Shipment Section
    doc.append("links", {
        "type": "Card Break",
        "label": "Shipment Management",
        "icon": "shipment-truck"
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

    # 📄 Logs Section
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

    # ⚙️ Configuration Section
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

    # -------------------------------
    # Save
    # -------------------------------
    doc.save(ignore_permissions=True)