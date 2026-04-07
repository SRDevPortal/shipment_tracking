import frappe


def create_module_def():
    module_name = "Shipment Tracking"

    if not frappe.db.exists("Module Def", module_name):
        doc = frappe.get_doc({
            "doctype": "Module Def",
            "module_name": module_name,
            "app_name": "shipment_tracking",
            "custom": 0,
            "icon": "shipment-truck"   # ✅ sidebar icon
        })
        doc.insert(ignore_permissions=True)
    else:
        doc = frappe.get_doc("Module Def", module_name)
        doc.icon = "shipment-truck"   # update if needed
        doc.save(ignore_permissions=True)