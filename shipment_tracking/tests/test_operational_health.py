from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from shipment_tracking.api.health import get_operational_health
from shipment_tracking.patches.v2_0.add_operational_indexes import INDEXES


class TestOperationalHealth(FrappeTestCase):
    def test_health_endpoint_is_system_manager_only(self):
        with patch.object(frappe, "only_for") as only_for, patch.object(
            frappe.db, "count", return_value=0
        ), patch.object(
            frappe.utils, "now_datetime", return_value="2026-10-30 12:00:00"
        ), patch.object(
            frappe.db,
            "sql",
            side_effect=[
                [],
                [],
                [frappe._dict(groups_count=0, extra_rows=0)],
            ],
        ):
            result = get_operational_health()

        only_for.assert_called_once_with("System Manager")
        self.assertEqual(result["unresolved_attempts"], 0)
        self.assertEqual(result["duplicate_identity_groups"], 0)

    def test_operational_indexes_cover_shipments_and_logs(self):
        self.assertEqual(
            {doctype for doctype, fields, name in INDEXES},
            {"Shipment Tracking Shipment", "Shipment Tracking Sync Log"},
        )
        self.assertIn(
            (
                "Shipment Tracking Sync Log",
                ["action", "status", "creation"],
                "idx_sync_log_action_status_creation",
            ),
            INDEXES,
        )
