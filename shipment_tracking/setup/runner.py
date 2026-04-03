import frappe
from .sales_invoice import apply as apply_sales_invoice
from .patient_encounter import apply as apply_patient_encounter


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
        # 2. Apply customizations (safe after reload)
        # --------------------------------------------------
        apply_sales_invoice()
        apply_patient_encounter()

        # --------------------------------------------------
        # 3. Commit (important for scripts)
        # --------------------------------------------------
        frappe.db.commit()
        frappe.clear_cache()

        frappe.logger().info("Shipment Tracking setup completed successfully")

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Shipment Tracking Setup Failed")
        raise