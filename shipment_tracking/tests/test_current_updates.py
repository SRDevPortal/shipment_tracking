from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from shipment_tracking.api.order import create_order_for_sales_invoice
from shipment_tracking.api.order_webhook import order_status_update
from shipment_tracking.api.utils import normalize_tracking_status
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

    @patch("shipment_tracking.api.order_webhook.frappe.db.commit")
    @patch("shipment_tracking.api.order_webhook.mirror_summary_fields")
    @patch("shipment_tracking.api.order_webhook.repair_shipment_links")
    @patch("shipment_tracking.api.order_webhook.get_or_create_shipment")
    @patch("shipment_tracking.api.order_webhook.validate_webhook_secret")
    @patch("shipment_tracking.api.order_webhook.frappe.get_single")
    @patch("shipment_tracking.api.order_webhook.frappe.db.get_value")
    def test_webhook_updates_normalized_status(
        self,
        get_value,
        get_single,
        validate_secret,
        get_or_create_shipment,
        repair_links,
        mirror_fields,
        commit,
    ):
        shipment = FakeShipment()
        get_value.return_value = None
        get_single.return_value = SimpleNamespace()
        get_or_create_shipment.return_value = shipment
        request = SimpleNamespace(
            get_json=lambda: {
                "order_id": "ORD-TEST",
                "order_status": "ofd",
                "courier_partner": "Test Courier",
            }
        )

        with patch.object(frappe, "request", request):
            result = order_status_update()

        self.assertTrue(result["success"])
        self.assertEqual(shipment.shipkia_status, "ofd")
        self.assertEqual(shipment.normalized_status, "Out for Delivery")
        self.assertTrue(shipment.saved)
        commit.assert_called_once()

    @patch("shipment_tracking.api.order.create_or_update_shipment_from_order_response")
    @patch("shipment_tracking.api.order.get_linked_encounter")
    @patch("shipment_tracking.api.order.first_order_id")
    @patch("shipment_tracking.api.order.safe_response_json")
    @patch("shipment_tracking.api.order.requests.post")
    @patch("shipment_tracking.api.order.make_sync_log")
    @patch("shipment_tracking.api.order.build_payload_from_sales_invoice")
    @patch("shipment_tracking.api.order.get_settings")
    @patch("shipment_tracking.api.order.frappe.get_doc")
    def test_order_links_invoice_before_success_commit(
        self,
        get_doc,
        get_settings,
        build_payload,
        make_sync_log,
        requests_post,
        safe_response_json,
        first_order_id,
        get_linked_encounter,
        create_shipment,
    ):
        invoice = SimpleNamespace(name="SINV-TEST", docstatus=1, si_shipkia_order_id=None)
        get_doc.return_value = invoice
        get_settings.return_value = SimpleNamespace(
            enabled=1,
            create_order_url="https://example.invalid",
            get_password=lambda *args, **kwargs: "",
        )
        build_payload.return_value = {"billing_same_as_delivery": True}
        log = SimpleNamespace(
            status=None,
            shipkia_order_id=None,
            http_status=None,
            response_json=None,
            error_message=None,
            save=Mock(),
        )
        make_sync_log.return_value = log
        requests_post.return_value = SimpleNamespace(status_code=200)
        safe_response_json.return_value = {"message": {}}
        first_order_id.return_value = "ORD-TEST"
        get_linked_encounter.return_value = None
        create_shipment.return_value = SimpleNamespace(name="SHIP-TEST")

        call_order = []
        with (
            patch(
                "shipment_tracking.api.order.frappe.db.set_value",
                side_effect=lambda *args, **kwargs: call_order.append("invoice-linked"),
            ),
            patch(
                "shipment_tracking.api.order.frappe.db.commit",
                side_effect=lambda: call_order.append("commit"),
            ),
        ):
            result = create_order_for_sales_invoice("SINV-TEST")

        self.assertEqual(result["order_id"], "ORD-TEST")
        self.assertEqual(call_order, ["invoice-linked", "commit"])
