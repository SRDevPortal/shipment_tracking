app_name = "shipment_tracking"
app_title = "Shipment Tracking"
app_publisher = "SRIAAS"
app_description = "Shipkia shipment sync and tracking for ERPNext."
app_email = "webdevelopersriaas@gmail.com"
app_license = "MIT"

after_install = "shipment_tracking.install.after_install"
after_migrate = "shipment_tracking.install.after_migrate"

doctype_js = {
    "Sales Invoice": [
        "public/js/sales_invoice_shipment_tracking.js",
    ],
    "Patient Encounter": [
        "public/js/patient_encounter_shipment_tracking.js",
    ],
}

permission_query_conditions = {
    "Shipment Tracking Support Ticket": "shipment_tracking.api.support.get_support_ticket_permission_query",
}

has_permission = {
    "Shipment Tracking Support Ticket": "shipment_tracking.api.support.has_support_ticket_permission",
}

scheduler_events = {
    "daily": [
        "shipment_tracking.api.support.cleanup_successful_support_update_logs",
    ],
}

fixtures = []
