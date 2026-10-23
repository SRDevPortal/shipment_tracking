from datetime import datetime
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from shipment_tracking.api.v2 import client, responses, tracking_params
from shipment_tracking.services import tracking as tracking_service


SAMPLE_RESPONSE = {
    "success": True,
    "result": {
        "company": "Test Company",
        "company_id": "CUST-1",
        "tracking_id": "84785910736400",
        "order_details": {
            "id": "ORD-2026-00005",
            "reference_id": "REF-1",
            "delivery_address": "private address",
            "awb": "84785910736400",
            "courier_partner": "delhivery",
            "estimated_delivery_date": None,
            "delivered_date": None,
        },
        "shipment_timeline": [
            {
                "id": "1",
                "stage": "In-Transit",
                "status": "Out for Delivery",
                "status_time": "2026-08-22T11:40:58.000Z",
                "location": "Delhi",
                "instructions": "Out for delivery",
            },
            {
                "id": "2",
                "stage": "In-Transit",
                "status": "Reached Destination Hub",
                "status_time": "2026-08-22T11:45:11.000Z",
                "location": "Bengaluru",
                "instructions": "Consignee Unavailable",
            },
        ],
    },
    "traceId": "trace-1",
}


class FakeShipment:
    def __init__(self):
        self.name = "SHIP-1"
        self.shipkia_order_id = "ORD-2026-00005"
        self.shipkia_tracking_id = None
        self.shipkia_awb_number = "84785910736400"
        self.shipkia_status = "Delivered"
        self.normalized_status = "Delivered"
        self.shipkia_stage = "Delivered"
        self.shipkia_status_detail = "Delivered"
        self.company = None
        self.company_id = None
        self.payment_mode = None
        self.delivery_partner = "delhivery"
        self.delivery_location = None
        self.shipkia_estimated_delivery = None
        self.shipkia_delivered_on = None
        self.last_synced_on = datetime(2026, 8, 23, 10, 0)
        self.raw_latest_response = None
        self.sales_invoice = "SINV-1"
        self.patient_encounter = "ENC-1"
        self.events = []
        self.saved = False

    def set(self, fieldname, value):
        setattr(self, fieldname, value)

    def append(self, fieldname, value):
        self.events.append(frappe._dict(value))

    def save(self, ignore_permissions=False):
        self.saved = True


class TestV2Tracking(TestCase):
    def test_tracking_params_use_tracking_id_then_awb(self):
        shipment = SimpleNamespace(
            shipkia_tracking_id="TRACK-1",
            shipkia_awb_number="AWB-1",
        )
        self.assertEqual(
            tracking_params.build_tracking_params(shipment),
            {"tracking_id": "TRACK-1"},
        )
        shipment.shipkia_tracking_id = None
        self.assertEqual(
            tracking_params.build_tracking_params(shipment),
            {"tracking_id": "AWB-1"},
        )

    def test_tracking_requires_identifier(self):
        shipment = SimpleNamespace(shipkia_tracking_id=None, shipkia_awb_number=None)
        with self.assertRaises(frappe.ValidationError):
            tracking_params.build_tracking_params(shipment)
        self.assertEqual(frappe.local.response["http_status_code"], 409)

    def test_v2_refresh_requires_tracking_id_or_awb(self):
        from shipment_tracking.api import tracking
        shipment = SimpleNamespace(
            shipkia_order_id="ORD-1",
            shipkia_tracking_id=None,
            shipkia_awb_number=None,
        )
        self.assertTrue(
            tracking._tracking_identifier_available(shipment, "New OMS")
        )
        shipment.shipkia_awb_number = "AWB-1"
        self.assertTrue(
            tracking._tracking_identifier_available(shipment, "New OMS")
        )
        shipment.shipkia_awb_number = None
        self.assertTrue(
            tracking._tracking_identifier_available(shipment, "Legacy")
        )

    def test_client_gets_order_details_from_configured_url(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "success": True,
            "result": {"value": {"id": "ORD-1"}},
        }
        account = SimpleNamespace(
            order_details_url="https://api.shipkia.com/oms/orders/records",
            get_password=lambda *args, **kwargs: "api-key",
        )
        with patch.object(client.requests, "get", return_value=response) as request:
            returned_response, body = client.get_order_details(account, "ORD/1")
        self.assertIs(returned_response, response)
        self.assertTrue(body["success"])
        self.assertEqual(
            request.call_args.args[0],
            "https://api.shipkia.com/oms/orders/records/ORD%2F1",
        )
        self.assertEqual(request.call_args.kwargs["headers"]["x-api-key"], "api-key")

    def test_order_details_response_maps_awb_and_order_state(self):
        body = {
            "success": True,
            "result": {
                "value": {
                    "id": "ORD-2026-00005",
                    "awb": "AWB-1",
                    "stage": "Shipped",
                    "status": "In Transit",
                    "courier_partner": "delhivery",
                    "courier_mode": "Surface",
                    "updated_at": "2026-10-23T10:00:00.000Z",
                }
            },
        }
        data = responses.order_details_from_response(
            body,
            "ORD-2026-00005",
        )
        self.assertEqual(data["awb"], "AWB-1")
        self.assertEqual(data["status"], "In Transit")
        self.assertEqual(data["courier_mode"], "Surface")

    def test_client_uses_get_query_and_api_key(self):
        response = Mock(status_code=200)
        response.json.return_value = SAMPLE_RESPONSE
        account = SimpleNamespace(
            order_tracking_url="https://api.shipkia.com/oms/orders/get_order_tracking",
            api_base_url="https://api.shipkia.com",
            get_password=lambda *args, **kwargs: "api-key",
        )
        with patch.object(client.requests, "get", return_value=response) as request:
            returned_response, body = client.get_tracking(account, "TRACK-1")
        self.assertIs(returned_response, response)
        self.assertTrue(body["success"])
        kwargs = request.call_args.kwargs
        self.assertEqual(kwargs["params"], {"tracking_id": "TRACK-1"})
        self.assertEqual(kwargs["headers"]["x-api-key"], "api-key")
        self.assertEqual(kwargs["timeout"], 60)

    def test_response_uses_newest_timeline_event(self):
        data = responses.tracking_from_response(
            SAMPLE_RESPONSE,
            "ORD-2026-00005",
        )
        self.assertEqual(data["status"], "Reached Destination Hub")
        self.assertEqual(data["stage"], "In-Transit")
        self.assertEqual(data["awb"], "84785910736400")
        self.assertEqual(data["courier_partner"], "delhivery")
        self.assertEqual(len(data["timeline"]), 2)

    def test_response_rejects_order_mismatch(self):
        with self.assertRaises(ValueError):
            responses.tracking_from_response(SAMPLE_RESPONSE, "OTHER-ORDER")

    def test_stale_manual_result_adds_history_without_regressing_summary(self):
        shipment = FakeShipment()
        data = responses.tracking_from_response(
            SAMPLE_RESPONSE,
            "ORD-2026-00005",
        )
        with (
            patch.object(tracking_service, "mirror_summary_fields"),
            patch.object(tracking_service, "notify_shipment_status_transition") as notify,
        ):
            stale = tracking_service.apply_tracking_data(
                shipment,
                data,
                SAMPLE_RESPONSE,
            )
        self.assertTrue(stale)
        self.assertEqual(shipment.shipkia_status, "Delivered")
        self.assertEqual(shipment.normalized_status, "Delivered")
        self.assertEqual(len(shipment.events), 2)
        self.assertTrue(shipment.saved)
        notify.assert_not_called()

    def test_sensitive_delivery_address_is_removed_from_storage(self):
        from shipment_tracking.api.v2 import tracking
        stored = tracking.response_for_storage(SAMPLE_RESPONSE)
        self.assertNotIn("delivery_address", stored["result"]["order_details"])
        self.assertIn("delivery_address", SAMPLE_RESPONSE["result"]["order_details"])

    def test_refresh_without_awb_uses_order_details_only(self):
        from shipment_tracking.api.v2 import tracking

        details_response = Mock(status_code=200)
        details_body = {
            "success": True,
            "result": {"value": {"id": "ORD-1", "stage": "New", "status": "New"}},
        }
        with (
            patch.object(tracking, "get_order_details", return_value=(details_response, details_body)),
            patch.object(tracking, "get_tracking") as get_tracking,
        ):
            response, body = tracking.send(
                SimpleNamespace(),
                {"order_id": "ORD-1", "tracking_id": None},
            )

        self.assertIs(response, details_response)
        self.assertEqual(body["order_details_response"], details_body)
        get_tracking.assert_not_called()

    def test_refresh_resolves_awb_then_requests_tracking(self):
        from shipment_tracking.api.v2 import tracking

        account = SimpleNamespace()
        details_response = Mock(status_code=200)
        details_body = {
            "success": True,
            "result": {"value": {"id": "ORD-1", "awb": "AWB-1"}},
        }
        tracking_response = Mock(status_code=200)
        with (
            patch.object(tracking, "get_order_details", return_value=(details_response, details_body)),
            patch.object(
                tracking,
                "get_tracking",
                return_value=(tracking_response, SAMPLE_RESPONSE),
            ) as get_tracking,
        ):
            response, body = tracking.send(
                account,
                {"order_id": "ORD-1", "tracking_id": None},
            )

        self.assertIs(response, tracking_response)
        self.assertEqual(body["order_details_response"], details_body)
        self.assertEqual(body["tracking_response"], SAMPLE_RESPONSE)
        get_tracking.assert_called_once_with(account, "AWB-1")

    def test_comparison_reports_only_changed_tracking_fields(self):
        shipment = FakeShipment()
        shipment.shipkia_status = "Ready to Ship"
        shipment.shipkia_stage = "Ready to Ship"
        shipment.delivery_partner = "bluedart"
        shipment.courier_partner_mode = None
        shipment.shipkia_awb_number = "AWB-1"
        shipment.shipkia_tracking_id = "AWB-1"
        shipment.last_synced_on = datetime(2026, 10, 23, 18, 18)
        data = {
            "awb": "AWB-1",
            "tracking_id": "AWB-1",
            "stage": "In Transit",
            "status": "In Transit",
            "courier_partner": "Delhivery",
            "courier_mode": "Express",
            "status_time": "2026-10-23 18:42:00",
        }

        changes, identity_changed, provider_older = tracking_service.compare_tracking_data(
            shipment,
            data,
        )

        self.assertEqual(
            [row["label"] for row in changes],
            ["Stage", "Status", "Courier", "Mode", "Last Updated"],
        )
        self.assertFalse(identity_changed)
        self.assertFalse(provider_older)

    def test_comparison_returns_match_for_same_provider_state(self):
        shipment = FakeShipment()
        shipment.shipkia_status = "Ready to Ship"
        shipment.shipkia_stage = "Ready to Ship"
        shipment.delivery_partner = "bluedart"
        shipment.courier_partner_mode = None
        shipment.shipkia_awb_number = "AWB-1"
        shipment.shipkia_tracking_id = "AWB-1"
        shipment.last_synced_on = datetime(2026, 10, 23, 18, 18)
        data = {
            "awb": "AWB-1",
            "tracking_id": "AWB-1",
            "stage": "Ready to Ship",
            "status": "Ready to Ship",
            "courier_partner": "BLUEDART",
            "status_time": "2026-10-23 18:18:00",
        }

        changes, identity_changed, provider_older = tracking_service.compare_tracking_data(
            shipment,
            data,
        )

        self.assertEqual(changes, [])
        self.assertFalse(identity_changed)
        self.assertFalse(provider_older)

    def test_order_details_cancellation_overrides_older_tracking_timeline(self):
        from shipment_tracking.api.v2 import tracking

        details_body = {
            "success": True,
            "result": {
                "value": {
                    "id": "ORD-2026-00005",
                    "awb": "84785910736400",
                    "stage": "Cancelled",
                    "status": "Cancelled",
                    "courier_partner": "delhivery",
                    "courier_mode": "Express",
                    "updated_at": "2026-10-23T14:12:08.313Z",
                }
            },
        }
        combined = {
            "order_details_response": details_body,
            "tracking_response": SAMPLE_RESPONSE,
        }

        data = tracking.parse_response(
            combined,
            SimpleNamespace(shipkia_order_id="ORD-2026-00005"),
        )

        self.assertEqual(data["stage"], "Cancelled")
        self.assertEqual(data["status"], "Cancelled")
        self.assertEqual(data["status_time"], "2026-10-23T14:12:08.313Z")
        self.assertEqual(len(data["timeline"]), 2)

    def test_refresh_with_existing_awb_still_checks_order_details(self):
        from shipment_tracking.api.v2 import tracking

        account = SimpleNamespace()
        details_response = Mock(status_code=200)
        details_body = {
            "success": True,
            "result": {
                "value": {
                    "id": "ORD-1",
                    "awb": "AWB-1",
                    "stage": "Cancelled",
                    "status": "Cancelled",
                }
            },
        }
        tracking_response = Mock(status_code=200)
        with (
            patch.object(
                tracking,
                "get_order_details",
                return_value=(details_response, details_body),
            ) as get_order_details,
            patch.object(
                tracking,
                "get_tracking",
                return_value=(tracking_response, SAMPLE_RESPONSE),
            ),
        ):
            tracking.send(
                account,
                {"order_id": "ORD-1", "tracking_id": "AWB-1"},
            )

        get_order_details.assert_called_once_with(account, "ORD-1")
