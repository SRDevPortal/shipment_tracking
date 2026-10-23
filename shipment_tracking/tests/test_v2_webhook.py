from contextlib import nullcontext
from datetime import datetime
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from shipment_tracking.api.v2 import order_webhook


class FakeShipment:
    def __init__(self):
        self.name = "SHIP-TEST"
        self.sales_invoice = "SINV-TEST"
        self.patient_encounter = None
        self.shipkia_status = None
        self.normalized_status = None
        self.shipkia_stage = None
        self.shipkia_awb_number = None
        self.delivery_partner = None
        self.courier_partner_mode = None
        self.shipkia_status_detail = None
        self.shipkia_delivered_on = None
        self.last_synced_on = None
        self.events = []

    def append(self, fieldname, value):
        self.events.append(frappe._dict(value))

    def reload(self):
        return self


class TestV2Webhook(TestCase):
    def test_sample_payload_maps_to_shipment_and_event(self):
        shipment = FakeShipment()
        previous = order_webhook.apply_status(shipment, {
            "order_id": "ORD-2026-00003",
            "awb": "LUAC0001705472",
            "stage": "Ready to Pickup",
            "status": "Pickup Scheduled",
            "courier_partner": "ekart",
            "courier_partner_mode": "ekart surface",
            "status_time": "2026-10-22T12:25:44.690Z",
            "instructions": "Pickup scheduled",
        })
        self.assertIsNone(previous)
        self.assertEqual(shipment.shipkia_awb_number, "LUAC0001705472")
        self.assertEqual(shipment.shipkia_stage, "Ready to Pickup")
        self.assertEqual(shipment.shipkia_status, "Pickup Scheduled")
        self.assertEqual(shipment.normalized_status, "Pending Pickup")
        self.assertEqual(shipment.delivery_partner, "ekart")
        self.assertEqual(shipment.courier_partner_mode, "ekart surface")
        self.assertEqual(shipment.shipkia_status_detail, "Pickup scheduled")
        self.assertIsNone(shipment.last_synced_on.tzinfo)
        self.assertEqual(shipment.events[0].detail, "Pickup scheduled")
        self.assertEqual(shipment.events[0].location, "ekart surface")

    def test_authentication_accepts_dedicated_webhook_secret(self):
        account = SimpleNamespace(
            enable_webhook_security=1,
            get_password=lambda *args, **kwargs: "webhook-key",
        )
        with patch.object(order_webhook, "request_header", side_effect=lambda name: {
            "X-Webhook-Secret": "webhook-key"
        }.get(name)):
            order_webhook.authenticate(account)

    def test_event_headers_accept_created_and_updated_records(self):
        for record_event in ("records_created", "records_updated"):
            with self.subTest(record_event=record_event), patch.object(
                order_webhook,
                "request_header",
                side_effect=lambda name, value=record_event: {
                    "X-Shipkia-Event": "order_tracking",
                    "X-Shipkia-Record-Event": value,
                }.get(name),
            ):
                order_webhook.validate_event_headers()

    def test_event_headers_reject_unknown_record_event(self):
        with patch.object(order_webhook, "request_header", side_effect=lambda name: {
            "X-Shipkia-Event": "order_tracking",
            "X-Shipkia-Record-Event": "records_deleted",
        }.get(name)):
            with self.assertRaises(frappe.ValidationError):
                order_webhook.validate_event_headers()
            self.assertEqual(frappe.local.response["http_status_code"], 400)

    def test_event_headers_are_required(self):
        for missing_header in ("X-Shipkia-Event", "X-Shipkia-Record-Event"):
            headers = {
                "X-Shipkia-Event": "order_tracking",
                "X-Shipkia-Record-Event": "records_updated",
            }
            headers.pop(missing_header)
            with self.subTest(missing_header=missing_header), patch.object(
                order_webhook,
                "request_header",
                side_effect=lambda name, values=headers: values.get(name),
            ):
                with self.assertRaises(frappe.ValidationError):
                    order_webhook.validate_event_headers()
                self.assertEqual(frappe.local.response["http_status_code"], 400)

    def test_older_status_time_is_stale(self):
        shipment = FakeShipment()
        shipment.last_synced_on = datetime(2026, 10, 23, 13, 0, 0)
        self.assertTrue(
            order_webhook.is_stale_event(
                shipment,
                datetime(2026, 10, 23, 12, 59, 59),
            )
        )
        self.assertFalse(
            order_webhook.is_stale_event(
                shipment,
                datetime(2026, 10, 23, 13, 0, 0),
            )
        )

    def test_duplicate_event_returns_success_without_applying_again(self):
        shipment = FakeShipment()
        account = SimpleNamespace(name="New OMS")
        request = SimpleNamespace(get_json=lambda: {"order_id": "ORD-2026-00003"})
        headers = {
            "X-Shipkia-Event-Id": "event-1",
            "X-Shipkia-Event": "order_tracking",
            "X-Shipkia-Record-Event": "records_updated",
        }
        with (
            patch.object(frappe, "request", request),
            patch.object(order_webhook, "request_header", side_effect=lambda name: headers.get(name)),
            patch.object(order_webhook, "get_owned_shipment", return_value=(shipment, account)),
            patch.object(order_webhook, "authenticate"),
            patch.object(order_webhook, "validate_event_headers"),
            patch.object(
                frappe,
                "cache",
                return_value=SimpleNamespace(lock=lambda *args, **kwargs: nullcontext()),
            ),
            patch.object(frappe.db, "get_value", return_value="LOG-EXISTING"),
            patch.object(order_webhook, "apply_status") as apply_status,
        ):
            result = order_webhook.order_status_update()
        self.assertTrue(result["success"])
        self.assertTrue(result["duplicate"])
        apply_status.assert_not_called()
