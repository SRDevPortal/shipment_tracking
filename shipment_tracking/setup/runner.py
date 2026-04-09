import frappe
from shipment_tracking.setup.sales_invoice import apply as apply_sales_invoice
from shipment_tracking.setup.patient_encounter import apply as apply_patient_encounter
from shipment_tracking.setup.module import create_module_def
from shipment_tracking.workspace import create_workspace


def setup_all(skip_reload=False):
    try:
        # --------------------------------------------------
        # 1. Reload doctypes ONLY when needed
        # --------------------------------------------------
        if not skip_reload:
            doctypes = [
                "shipment_tracking_settings",
                "shipment_tracking_shipment",
                "shipment_tracking_shipment_event",
                "shipment_tracking_sync_log",
            ]

            for dt in doctypes:
                frappe.reload_doc("shipment_tracking", "doctype", dt)

        # --------------------------------------------------
        # 2. Apply customizations
        # --------------------------------------------------
        apply_sales_invoice()
        apply_patient_encounter()

        # --------------------------------------------------
        # 3. Create Module Def (only if not exists)
        # --------------------------------------------------
        if not frappe.db.exists("Module Def", "Shipment Tracking"):
            create_module_def()

        # --------------------------------------------------
        # 4. Create Workspace (only if not exists)
        # --------------------------------------------------
        if not frappe.db.exists("Workspace", {"module": "Shipment Tracking"}):
            create_workspace()

        # --------------------------------------------------
        # 5. Clear cache
        # --------------------------------------------------
        frappe.clear_cache()

        frappe.logger("shipment_tracking").info(
            "Shipment Tracking setup completed successfully"
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Shipment Tracking Setup Failed")
        raise