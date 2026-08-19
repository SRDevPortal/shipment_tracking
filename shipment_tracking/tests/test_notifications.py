from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from shipment_tracking.notifications import (
    build_event_key,
    invoice_template_preview,
    is_event_enabled,
    notify_shipment_status_transition,
    shipment_template_preview,
)
from shipment_tracking.shipment_tracking.doctype.shipment_tracking_settings.shipment_tracking_settings import (
    ShipmentTrackingSettings,
)


class TestShipmentNotifications(FrappeTestCase):
    def test_builds_deterministic_event_keys(self):
        self.assertEqual(
            build_event_key(
                "sales_invoice_generated",
                sales_invoice="SINV-0001",
            ),
            "sales_invoice:SINV-0001:sales_invoice_generated",
        )
        self.assertEqual(
            build_event_key(
                "order_picked_up",
                shipment="SHIP-0001",
            ),
            "shipment:SHIP-0001:order_picked_up",
        )

    def test_master_switch_disables_all_events(self):
        settings = frappe._dict(
            enable_whatsapp_notifications=0,
            enable_sales_invoice_generated=1,
            enable_order_picked_up=1,
            enable_out_for_delivery=1,
        )
        for event_type in (
            "sales_invoice_generated",
            "order_picked_up",
            "out_for_delivery",
        ):
            self.assertFalse(is_event_enabled(settings, event_type, patient="PAT-0001"))

    def test_event_switches_are_independent(self):
        settings = frappe._dict(
            enable_whatsapp_notifications=1,
            enable_sales_invoice_generated=1,
            enable_order_picked_up=0,
            enable_out_for_delivery=1,
        )
        self.assertTrue(is_event_enabled(settings, "sales_invoice_generated", patient="PAT-0001"))
        self.assertFalse(is_event_enabled(settings, "order_picked_up", patient="PAT-0001"))
        self.assertTrue(is_event_enabled(settings, "out_for_delivery", patient="PAT-0001"))

    def test_patient_notification_hub_engine_disables_legacy_events(self):
        settings = frappe._dict(
            whatsapp_notification_engine="Patient Notification Hub",
            enable_whatsapp_notifications=1,
            enable_sales_invoice_generated=1,
        )

        self.assertFalse(is_event_enabled(settings, "sales_invoice_generated", patient="PAT-0001"))

    @patch("shipment_tracking.shipment_tracking.doctype.shipment_tracking_settings.shipment_tracking_settings.frappe.get_installed_apps", return_value=[])
    def test_hub_engine_requires_installed_hub(self, get_installed_apps):
        settings = SimpleNamespace()

        with self.assertRaises(frappe.ValidationError):
            ShipmentTrackingSettings.validate_patient_notification_hub(settings)

    def test_pilot_patient_restricts_events(self):
        settings = frappe._dict(
            enable_whatsapp_notifications=1,
            enable_order_picked_up=1,
            whatsapp_test_patient="PAT-0001",
        )
        self.assertTrue(is_event_enabled(settings, "order_picked_up", patient="PAT-0001"))
        self.assertFalse(is_event_enabled(settings, "order_picked_up", patient="PAT-0002"))

    def test_invoice_template_preview_matches_approved_template(self):
        preview = invoice_template_preview(
            ["Jitendra Kumar", "SRI-26-000003", "27-07-2026", "INR 2160.00"]
        )

        self.assertIn("Hello Jitendra Kumar,", preview)
        self.assertIn(
            "Your sales invoice SRI-26-000003 dated 27-07-2026 has been generated successfully.",
            preview,
        )
        self.assertIn("Invoice Amount: INR 2160.00", preview)

    def test_shipment_template_previews_match_approved_templates(self):
        picked_up = shipment_template_preview(
            [
                "Jitendra Kumar",
                "ORD-10001",
                "AWB-10001",
                "Delhivery",
                "30-07-2026 23:59:59",
            ],
            "order_picked_up",
        )
        out_for_delivery = shipment_template_preview(
            ["Jitendra Kumar", "ORD-10001", "AWB-10001", "Delhivery"],
            "out_for_delivery",
        )

        self.assertIn("Your order ORD-10001 has been picked up", picked_up)
        self.assertIn("Estimated Delivery: 30-07-2026 23:59:59", picked_up)
        self.assertIn("Your order ORD-10001 is out for delivery.", out_for_delivery)
        self.assertIn("Please keep your phone available", out_for_delivery)

    @patch("shipment_tracking.notifications.create_notification")
    def test_picked_up_transition_emits_matching_event(self, create_notification):
        shipment = SimpleNamespace(
            name="SHIP-0001",
            patient="PAT-0001",
            sales_invoice="SINV-0001",
            shipkia_order_id="ORDER-0001",
            shipkia_awb_number="AWB-0001",
            delivery_partner="Courier",
            shipkia_estimated_delivery=None,
            shipkia_status="Picked Up",
            normalized_status="Picked Up",
        )

        notify_shipment_status_transition(shipment, "In Transit")

        create_notification.assert_called_once()
        self.assertEqual(create_notification.call_args.kwargs["event_type"], "order_picked_up")

    @patch("shipment_tracking.notifications.create_notification")
    def test_unchanged_status_does_not_emit_event(self, create_notification):
        shipment = SimpleNamespace(
            name="SHIP-0001",
            shipkia_status="Out for Delivery",
            normalized_status="Out for Delivery",
        )

        notify_shipment_status_transition(shipment, "Out for Delivery")

        create_notification.assert_not_called()
