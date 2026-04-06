app_name = "shipment_tracking"
app_title = "Shipment Tracking"
app_publisher = "SRIAAS"
app_description = "Shipkia shipment sync and tracking for ERPNext."
app_email = "webdevelopersriaas@gmail.com"
app_license = "mit"

after_install = "shipment_tracking.install.after_install"
after_migrate = "shipment_tracking.install.after_migrate"

doctype_js = {
    "Sales Invoice": [
        "public/js/sales_invoice_shipment_tracking.js",
    ],
}

fixtures = []