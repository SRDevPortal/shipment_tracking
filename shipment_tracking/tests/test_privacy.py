import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from shipment_tracking.api.order import make_sync_log, redact_order_payload_for_log
from shipment_tracking.api.order_webhook import order_status_update
from shipment_tracking.api.privacy import support_summary
from shipment_tracking.api.support import (
    refresh_support_ticket,
    request_hub_address_for_encounter,
    request_hub_address_for_invoice,
    request_reattempt_for_encounter,
    request_reattempt_for_invoice,
    support_ticket_update,
)


class ShipmentPrivacyTests(TestCase):
    def test_order_log_projection_masks_phone_without_mutating_provider_payload(self):
        payload = {
            "delivery_phone_number": "+91-9876543210",
            "billing_phone_number": "+91-9123456780",
            "delivery_full_name": "Synthetic Patient",
        }

        projected = redact_order_payload_for_log(payload)

        self.assertEqual(projected["delivery_phone_number"], "********3210")
        self.assertEqual(projected["billing_phone_number"], "********6780")
        self.assertEqual(payload["delivery_phone_number"], "+91-9876543210")
        self.assertEqual(payload["billing_phone_number"], "+91-9123456780")
        self.assertNotIn("9876543210", str(projected))
        self.assertNotIn("9123456780", str(projected))

    def test_sync_log_stores_only_projected_order_phone_values(self):
        captured = {}

        class Log:
            def insert(self, ignore_permissions=False):
                return self

        def get_doc(values):
            captured.update(values)
            return Log()

        payload = {
            "delivery_phone_number": "+91-9876543210",
            "billing_same_as_delivery": True,
        }
        with (
            patch("shipment_tracking.api.order.frappe.get_doc", side_effect=get_doc),
            patch("shipment_tracking.api.order.frappe.db.commit"),
        ):
            make_sync_log("Outbound", "Create Order", "Sales Invoice", "SINV-TEST", payload)

        stored = json.loads(captured["request_json"])
        self.assertEqual(stored["delivery_phone_number"], "********3210")
        self.assertNotIn("9876543210", captured["request_json"])
        self.assertEqual(payload["delivery_phone_number"], "+91-9876543210")

    def test_restricted_support_summary_drops_provider_details(self):
        source = {
            "success": True,
            "ticket": "LOCAL-TICKET",
            "latest_ticket_id": "PROVIDER-TICKET",
            "latest_response": "Call 9876543210 at the hub",
            "responses": [{"message": "Call 9876543210"}],
            "order_id": "ORDER-PRIVATE",
        }
        with (
            patch.object(frappe, "conf", {"privacy_shield_desk_enabled": True}),
            patch(
                "privacy_shield.policy.current_capabilities",
                return_value=SimpleNamespace(view_full=False),
            ),
        ):
            projected = support_summary(source)

        self.assertTrue(projected["details_restricted"])
        self.assertEqual(projected["ticket"], "LOCAL-TICKET")
        self.assertEqual(projected["latest_response"], "")
        self.assertEqual(projected["responses"], [])
        self.assertNotIn("latest_ticket_id", projected)
        self.assertNotIn("order_id", projected)
        self.assertNotIn("9876543210", str(projected))

    def test_full_view_support_summary_preserves_contract(self):
        source = {"latest_response": "Call 9876543210"}
        with (
            patch.object(frappe, "conf", {"privacy_shield_desk_enabled": True}),
            patch(
                "privacy_shield.policy.current_capabilities",
                return_value=SimpleNamespace(view_full=True),
            ),
        ):
            self.assertIs(support_summary(source), source)

    def test_side_effecting_endpoints_are_post_only(self):
        endpoints = (
            request_reattempt_for_invoice,
            request_hub_address_for_invoice,
            request_reattempt_for_encounter,
            request_hub_address_for_encounter,
            refresh_support_ticket,
            support_ticket_update,
            order_status_update,
        )
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint.__name__):
                self.assertEqual(
                    frappe.allowed_http_methods_for_whitelisted_func[endpoint],
                    ["POST"],
                )