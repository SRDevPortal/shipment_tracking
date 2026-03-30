import frappe
from .sales_invoice import apply as apply_sales_invoice
from .patient_encounter import apply as apply_patient_encounter


def setup_all():
    # Ensure DocType exists BEFORE linking
    frappe.reload_doc(
        "shipment_tracking",
        "doctype",
        "shipment_tracking_shipment"
    )

    # Now safe to create fields
    apply_sales_invoice()
    apply_patient_encounter()