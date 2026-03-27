from .sales_invoice import apply as apply_sales_invoice
from .patient_encounter import apply as apply_patient_encounter


def setup_all():
    apply_sales_invoice()
    apply_patient_encounter()
