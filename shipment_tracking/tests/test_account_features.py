from unittest import TestCase
from unittest.mock import patch
import frappe
from shipment_tracking.shipment_tracking.doctype.shipkia_account.shipkia_account import ShipkiaAccount


class TestAccountFeatures(TestCase):
    def account(self, **values):
        return frappe.get_doc({"doctype": "Shipkia Account", "platform": "Legacy", **values})

    def test_disabled_features_clear_all_values(self):
        account = self.account(order_details_url="https://example.invalid/orders", order_tracking_url="https://example.invalid/track", webhook_secret="old-secret",
            support_create_url="https://example.invalid/create", support_get_url="https://example.invalid/get",
            support_update_url="https://example.invalid/update", support_list_url="https://example.invalid/list",
            pickup_address="PKA00002", order_channel="maunal")
        account.validate()
        for field in ("order_details_url", "order_tracking_url", "webhook_secret", "support_create_url", "support_get_url", "support_update_url", "support_list_url"):
            self.assertIsNone(account.get(field))
        self.assertEqual(account.pickup_address, "PKA00002")
        self.assertEqual(account.order_channel, "maunal")

    def test_tracking_requires_url(self):
        account=self.account(enable_manual_tracking_refresh=1)
        with self.assertRaises(frappe.ValidationError):
            account.validate()
        account.order_tracking_url="https://example.invalid/track"
        account.validate()
        self.assertTrue(account.order_tracking_url)

    def test_v2_tracking_requires_both_urls(self):
        account = self.account(
            platform="New OMS",
            enable_manual_tracking_refresh=1,
            order_tracking_url="https://example.invalid/track",
        )
        with self.assertRaises(frappe.ValidationError):
            account.validate()
        account.order_details_url = "https://example.invalid/orders"
        account.validate()

    def test_webhook_requires_secret(self):
        account=self.account(enable_webhook_security=1)
        with patch.object(account,"get_password",return_value=""):
            with self.assertRaises(frappe.ValidationError):
                account.validate()
        account.webhook_secret="test-secret"
        account.validate()
        self.assertEqual(account.webhook_secret,"test-secret")

    def test_support_only_requires_create_and_get_urls(self):
        account=self.account(enable_support_ticket=1)
        with self.assertRaises(frappe.ValidationError):
            account.validate()
        account.support_create_url="https://example.invalid/create"
        with self.assertRaises(frappe.ValidationError):
            account.validate()
        account.support_get_url="https://example.invalid/get"
        account.validate()
        self.assertFalse(account.support_update_url)
        self.assertFalse(account.support_list_url)

    def test_optional_support_urls_must_use_https_when_supplied(self):
        account=self.account(enable_support_ticket=1,support_create_url="https://example.invalid/create",
                             support_get_url="https://example.invalid/get", support_list_url="http://example.invalid/list")
        with self.assertRaises(frappe.ValidationError):
            account.validate()

    def test_v2_uses_same_optional_feature_validation(self):
        account=self.account(platform="New OMS",enable_manual_tracking_refresh=1,order_details_url="https://example.invalid/orders",order_tracking_url="https://example.invalid/track",
                             default_parcel_length=10,default_parcel_breadth=10,
                             default_parcel_height=10,default_dead_weight=500)
        account.validate()

    def test_v2_rejects_dimensions_below_provider_minimum(self):
        account=self.account(platform="New OMS",default_parcel_length=10,default_parcel_breadth=10,
                             default_parcel_height=5,default_dead_weight=500)
        with self.assertRaises(frappe.ValidationError):
            account.validate()
        account.default_parcel_height=10
        account.validate()

    def test_v2_allows_empty_parcel_defaults(self):
        account=self.account(platform="New OMS",default_parcel_length=None,default_parcel_breadth=None,
                             default_parcel_height=None,default_dead_weight=None)
        account.validate()

    def test_schema_visibility_and_required_fields(self):
        meta=frappe.get_meta("Shipkia Account")
        for field in ("order_details_url", "order_tracking_url", "webhook_secret", "support_create_url", "support_get_url"):
            self.assertTrue(meta.get_field(field).depends_on)
            self.assertTrue(meta.get_field(field).mandatory_depends_on)
        for field in ("support_update_url", "support_list_url"):
            self.assertTrue(meta.get_field(field).depends_on)
            self.assertFalse(meta.get_field(field).mandatory_depends_on)
