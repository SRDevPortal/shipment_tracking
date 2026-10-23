from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from shipment_tracking.api.order import create_order_for_sales_invoice
from shipment_tracking.api.order_webhook import order_status_update
from shipment_tracking.services.statuses import normalize_tracking_status
from shipment_tracking.patches.v1_0.add_tracking_indexes import INDEXES


class FakeShipment:
    def __init__(self, status="In Transit"):
        self.name = "TEST-SHIPMENT"
        self.sales_invoice = None
        self.patient_encounter = None
        self.shipkia_status = status
        self.normalized_status = normalize_tracking_status(status)
        self.shipkia_stage = None
        self.shipkia_awb_number = None
        self.delivery_partner = None
        self.shipkia_estimated_delivery = None
        self.shipkia_delivered_on = None
        self.raw_latest_response = None
        self.events = []
        self.saved = False

    def append(self, fieldname, value):
        self.events.append(frappe._dict(value))

    def save(self, ignore_permissions=False):
        self.saved = True


class TestCurrentShipmentUpdates(FrappeTestCase):
    def test_shipkia_status_aliases(self):
        self.assertEqual(normalize_tracking_status("pickup completed"), "Picked Up")
        self.assertEqual(normalize_tracking_status("OFD"), "Out for Delivery")
        self.assertEqual(normalize_tracking_status("Custom Provider Status"), "Custom Provider Status")

    def test_tracking_indexes_do_not_reference_notification_tables(self):
        doctypes = {doctype for doctype, fields, index_name in INDEXES}
        self.assertEqual(doctypes, {"Sales Invoice", "Shipment Tracking Shipment"})

    def test_webhook_updates_normalized_status(self):
        shipment = FakeShipment()
        request = SimpleNamespace(get_json=lambda: {
            "order_id": "ORD-TEST", "order_status": "ofd", "courier_partner": "Test Courier"})
        with (
            patch("shipment_tracking.api.order_webhook.legacy_settings"),
            patch("shipment_tracking.api.order_webhook.validate_webhook_secret"),
            patch("shipment_tracking.api.order_webhook.frappe.get_all", return_value=[shipment.name]),
            patch("shipment_tracking.api.order_webhook.frappe.get_doc", return_value=shipment),
            patch("shipment_tracking.api.order_webhook.repair_shipment_links"),
            patch("shipment_tracking.api.order_webhook.mirror_summary_fields"),
            patch("shipment_tracking.api.order_webhook.frappe.utils.now_datetime", return_value="2026-10-22 12:00:00"),
            patch("shipment_tracking.api.order_webhook.frappe.db.commit") as commit,
            patch.object(frappe, "request", request),
        ):
            result = order_status_update()
        self.assertTrue(result["success"])
        self.assertEqual(shipment.normalized_status, "Out for Delivery")
        self.assertTrue(shipment.saved)
        commit.assert_called_once()

    def test_legacy_rpc_never_follows_default_account(self):
        with patch("shipment_tracking.services.orders.run", return_value={}) as run:
            create_order_for_sales_invoice("SINV-TEST")
        self.assertEqual(run.call_args.args[:2], ("SINV-TEST", "Legacy"))
