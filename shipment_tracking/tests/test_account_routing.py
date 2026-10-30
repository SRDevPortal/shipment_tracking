from contextlib import nullcontext, ExitStack
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
import frappe
from shipment_tracking.api.v2 import client as v2_client
from shipment_tracking.api.v2 import order as v2
from shipment_tracking.api.v2 import payload as v2_payload
from shipment_tracking.api.v2 import responses as v2_responses
from shipment_tracking.services import orders
from shipment_tracking.services.shipments import identity_key


def doc(**kwargs):
    return SimpleNamespace(**kwargs, get=lambda key, default=None: kwargs.get(key, default))


class TestAccountRouting(TestCase):
    def test_v2_money_uses_rupees(self):
        self.assertEqual(v2.money("12.345"), 12.35)
        self.assertEqual(v2.money("0.01"), 0.01)

    def test_response_path_is_explicit(self):
        self.assertEqual(v2.order_id_from_response({"result": {"value": {"id": "NEW-1"}}}, "result.value.id"), "NEW-1")
        for value in ({}, {"result": {"id": True}}, {"result": {"id": {"id": "wrong"}}}):
            self.assertIsNone(v2.order_id_from_response(value, "result.id"))

    def test_identity_is_account_scoped(self):
        self.assertNotEqual(identity_key("Legacy", "1"), identity_key("New OMS", "1"))

    def test_v2_source_has_no_legacy_or_product_api_dependency(self):
        import inspect
        source = "\n".join(inspect.getsource(module) for module in (v2, v2_payload, v2_client, v2_responses))
        self.assertNotIn("api.order import", source)
        self.assertNotIn("/products", source)
        self.assertIn("def get_tracking", source)
        self.assertIs(v2.build_payload, v2_payload.build_payload)
        self.assertIs(v2.send, v2_client.send)
        self.assertIs(v2.order_id_from_response, v2_responses.order_id_from_response)

    def test_v2_activation_requires_contract_confirmation(self):
        with self.assertRaises(frappe.ValidationError):
            v2.build_payload(doc(), doc(platform="New OMS", v2_contract_verified=0))

    def test_v2_payload_totals_and_partial_cod(self):
        account = doc(platform="New OMS", v2_contract_verified=1, pickup_address="PA-1", order_channel="ERPNext",
                      v2_order_id_path="result.id", get_password=lambda *a, **k: "test-key",
                      default_parcel_length=10, default_parcel_breadth=None, default_parcel_height=10,
                      default_dead_weight=500, default_volumetric_weight=1)
        invoice = doc(name="INV-TEST", currency="INR", shipping_address_name="ADDR", customer_address="ADDR",
                      contact_person=None, contact_mobile="9876543210", is_return=0, customer_name="Test",
                      grand_total=190, outstanding_amount=90, discount_amount=10, remarks="",
                      items=[doc(item_code="ITEM",item_name="Item",rate=100,qty=2,gst_hsn_code="1234",
                                 weight_per_unit=0.25,weight_uom="Kg")], taxes=[])
        address = doc(name="ADDR",country="India",address_line1="Shopian\u2013Kulgam Road",
                      address_line2="Patient\u2019s home\u00a0near hub",city="Delhi",state="Delhi",pincode="110001",phone=None)
        with patch.object(frappe,"get_doc",return_value=address):
            payload = v2.build_payload(invoice,account)
        self.assertEqual(payload["prepaid_amount"],100)
        self.assertEqual(payload["additional_discount"],10)
        self.assertEqual(payload["product_details"][0]["unit_price"],100)
        self.assertEqual(payload["product_details"][0]["weight"],250)
        self.assertEqual(payload["product_details"][0]["tax_preference"],"Inclusive")
        self.assertEqual(payload["dead_weight"],500)
        self.assertEqual(payload["length"],10)
        self.assertNotIn("breadth",payload)
        self.assertEqual(payload["delivery_phone"], "+91-9876543210")
        self.assertEqual(payload["delivery_address"], "Shopian-Kulgam Road")
        self.assertEqual(payload["delivery_landmark"], "Patient's home near hub")
        for undocumented in ("remaining_cod_amount", "total_order_value", "updated_at",
                             "volumetric_weight", "delivery_city", "delivery_state", "delivery_country"):
            self.assertNotIn(undocumented,payload)

    def test_v2_address_sanitizer_removes_unsupported_unicode(self):
        self.assertEqual(
            v2_payload.sanitize_shipkia_address(
                "Caf\u00e9 \u2014 Block \u201cA\u201d \u2603"
            ),
            "Cafe - Block 'A'",
        )

        self.assertEqual(v2_payload.sanitize_shipkia_address("\u2603\u2603"), "")
    def test_v2_converts_exclusive_invoice_rate_to_inclusive_api_price(self):
        account = doc(platform="New OMS", v2_contract_verified=1, pickup_address="PA-1", order_channel="ERPNext",
                      v2_order_id_path="result.id", get_password=lambda *a, **k: "test-key",
                      default_parcel_length=10, default_parcel_breadth=10, default_parcel_height=10,
                      default_dead_weight=500)
        invoice = doc(name="INV-TAX", currency="INR", shipping_address_name="ADDR", customer_address="ADDR",
                      contact_person=None, contact_mobile="9876543210", is_return=0, customer_name="Test",
                      grand_total=118, outstanding_amount=118, discount_amount=0, remarks="",
                      items=[doc(item_code="ITEM", item_name="Item", rate=100, qty=1, gst_hsn_code="1234",
                                 weight_per_unit=250, weight_uom="Gram")],
                      taxes=[doc(rate=18, charge_type="On Net Total", included_in_print_rate=0)])
        address = doc(name="ADDR", address_line1="Test address", address_line2="", pincode="110001", phone=None)
        with patch.object(frappe, "get_doc", return_value=address):
            payload = v2.build_payload(invoice, account)
        self.assertEqual(payload["product_details"][0]["unit_price"], 118)
        self.assertEqual(payload["product_details"][0]["tax_preference"], "Inclusive")
        self.assertEqual(payload["additional_discount"], 0)
        self.assertEqual(payload["transaction_charge"], 0)

    def test_v2_combines_exclusive_cgst_and_sgst_per_item(self):
        account = doc(platform="New OMS", v2_contract_verified=1, pickup_address="PA-1", order_channel="ERPNext",
                      v2_order_id_path="result.id", get_password=lambda *a, **k: "test-key",
                      default_parcel_length=10, default_parcel_breadth=10, default_parcel_height=10,
                      default_dead_weight=500)
        invoice = doc(name="INV-CGST", currency="INR", shipping_address_name="ADDR", customer_address="ADDR",
                      contact_person=None, contact_mobile="9876543210", is_return=0, customer_name="Test",
                      grand_total=118, outstanding_amount=118, discount_amount=0, remarks="",
                      items=[doc(item_code="ITEM", item_name="Item", rate=100, qty=1, gst_hsn_code="1234",
                                 weight_per_unit=250, weight_uom="Gram",
                                 item_tax_rate='{"Output Tax CGST - SR": 9, "Output Tax SGST - SR": 9, "Output Tax IGST - SR": 18}')],
                      taxes=[doc(rate=9, account_head="Output Tax CGST - SR", charge_type="On Net Total",
                                 included_in_print_rate=0),
                             doc(rate=9, account_head="Output Tax SGST - SR", charge_type="On Net Total",
                                 included_in_print_rate=0)])
        address = doc(name="ADDR", address_line1="Test address", address_line2="", pincode="110001", phone=None)
        with patch.object(frappe, "get_doc", return_value=address):
            payload = v2.build_payload(invoice, account)
        self.assertEqual(payload["product_details"][0]["tax_rate"], 18)
        self.assertEqual(payload["product_details"][0]["unit_price"], 118)
        self.assertEqual(payload["additional_discount"], 0)
        self.assertEqual(payload["transaction_charge"], 0)

    def test_v2_uses_only_tax_accounts_active_on_invoice(self):
        context = v2_payload.invoice_tax_context(doc(
            items=[doc(item_code="ITEM", item_tax_rate={
                "Output Tax CGST - SR": 9,
                "Output Tax SGST - SR": 9,
                "Output Tax IGST - SR": 18,
            })],
            taxes=[doc(rate=18, account_head="Output Tax IGST - SR", charge_type="On Net Total",
                       included_in_print_rate=1)],
        ))
        rate = v2_payload.effective_item_tax_rate(
            doc(item_code="ITEM", item_tax_rate={
                "Output Tax CGST - SR": 9,
                "Output Tax SGST - SR": 9,
                "Output Tax IGST - SR": 18,
            }), context,
        )
        self.assertEqual(rate, 18)

    def test_v2_supports_mixed_item_gst_rates(self):
        context = v2_payload.invoice_tax_context(doc(
            items=[
                doc(item_code="FIVE", item_tax_rate={"CGST": 2.5, "SGST": 2.5}),
                doc(item_code="EIGHTEEN", item_tax_rate={"CGST": 9, "SGST": 9}),
            ],
            taxes=[
                doc(rate=0, account_head="CGST", charge_type="On Net Total", included_in_print_rate=1),
                doc(rate=0, account_head="SGST", charge_type="On Net Total", included_in_print_rate=1),
            ],
        ))
        self.assertEqual(
            v2_payload.effective_item_tax_rate(doc(item_code="FIVE", item_tax_rate={"CGST": 2.5, "SGST": 2.5}), context), 5,
        )
        self.assertEqual(
            v2_payload.effective_item_tax_rate(doc(item_code="EIGHTEEN", item_tax_rate={"CGST": 9, "SGST": 9}), context), 18,
        )

    def test_v2_rejects_unsupported_tax_charge_type(self):
        invoice = doc(
            items=[doc(item_code="ITEM", item_tax_rate={"GST": 18})],
            taxes=[doc(rate=18, account_head="GST", charge_type="On Previous Row Total",
                       included_in_print_rate=0)],
        )
        with self.assertRaises(frappe.ValidationError):
            v2_payload.invoice_tax_context(invoice)


    def test_v2_send_uses_published_endpoint_and_api_key(self):
        account=doc(api_base_url="https://api.shipkia.com",create_order_url=None,
                    v2_order_id_path="result.id",get_password=lambda *a,**k:"test-key")
        response=doc(status_code=200,json=lambda:{"success":True,"result":{"id":"ORD-1"}})
        with patch.object(v2_client.requests,"post",return_value=response) as post:
            returned,body,order_id=v2.send(account,{"pickup_address":"PA-1"})
        self.assertEqual(order_id,"ORD-1")
        self.assertEqual(post.call_args.args[0],"https://api.shipkia.com/oms/orders")
        self.assertEqual(post.call_args.kwargs["headers"]["x-api-key"],"test-key")
        self.assertEqual(post.call_args.kwargs["json"],{"pickup_address":"PA-1"})

    def test_v2_rejects_two_hundred_response_without_success_confirmation(self):
        account=doc(api_base_url="https://api.shipkia.com",create_order_url=None,
                    v2_order_id_path="result.id",get_password=lambda *a,**k:"test-key")
        response=doc(status_code=200,json=lambda:{"success":False,"result":{"id":"ORD-1"}})
        with patch.object(v2_client.requests,"post",return_value=response):
            returned,body,order_id=v2.send(account,{})
        self.assertIsNone(order_id)

    def run_order(self, adapter, pending=False, previous=False, reason=None, persist_error=False, ui_mode=0):
        invoice = doc(name="INV-TEST", docstatus=1, customer="Test", check_permission=Mock(),
                      si_shipkia_order_id="OLD" if previous else None,
                      si_shipkia_shipment="OLD-SHIP" if previous else None)
        log = Mock(name="sync-log"); log.name="LOG-TEST"
        calls = []
        log.insert.return_value=log
        def get_doc(*args, **kwargs):
            if isinstance(args[0], dict):
                log.status=args[0]["status"]
                return log
            if args[0]=="Sales Invoice": return invoice
            if args[0]=="Shipment Tracking Shipment": return doc(shipkia_account="New OMS")
            return log
        def persist(*args):
            calls.append("linked")
            if persist_error: raise RuntimeError("local error")
            return doc(name="SHIP-TEST")
        with ExitStack() as stack:
            stack.enter_context(patch.object(frappe,"cache",return_value=Mock(lock=Mock(return_value=nullcontext()))))
            stack.enter_context(patch.object(frappe,"get_doc",side_effect=get_doc))
            stack.enter_context(patch.object(frappe.db,"exists",return_value=pending))
            stack.enter_context(patch.object(frappe.db,"commit",side_effect=lambda: calls.append("commit")))
            stack.enter_context(patch.object(frappe.db,"rollback"))
            stack.enter_context(patch.object(orders,"get_account",return_value=doc(name="New OMS")))
            stack.enter_context(patch.object(orders,"save_order_shipment",side_effect=persist))
            try:
                result=orders.run("INV-TEST","New OMS",adapter,force=int(previous),
                                  replacement_reason=reason,ui_mode=ui_mode)
                return result,log,calls
            except Exception as exc:
                return exc,log,calls

    def adapter(self, status=201, order_id="NEW-1"):
        return Mock(build_payload=Mock(return_value={"product_details":[]}),
                    send=Mock(return_value=(doc(status_code=status), {"result":{"id":order_id}}, order_id)))

    def test_journal_precedes_send_and_link_precedes_final_commit(self):
        adapter=self.adapter()
        result,log,calls=self.run_order(adapter)
        self.assertEqual(result["order_id"],"NEW-1")
        self.assertEqual(calls,["commit","linked","commit"])
        self.assertEqual(log.status,"Success")

    def test_pending_attempt_blocks_even_after_default_switch(self):
        adapter=self.adapter()
        result,log,calls=self.run_order(adapter,pending=True)
        self.assertIsInstance(result,frappe.ValidationError)
        adapter.send.assert_not_called()

    def test_network_timeout_is_uncertain(self):
        adapter=self.adapter();adapter.send.side_effect=TimeoutError()
        result,log,calls=self.run_order(adapter)
        self.assertIsInstance(result,frappe.ValidationError)
        self.assertEqual(log.status,"Uncertain")
        self.assertNotIn("linked",calls)

    def test_missing_id_and_server_error_are_uncertain(self):
        for adapter in (self.adapter(order_id=None),self.adapter(status=503)):
            result,log,calls=self.run_order(adapter)
            self.assertEqual(log.status,"Uncertain")
            self.assertNotIn("linked",calls)

    def test_client_rejection_is_failed(self):
        result,log,calls=self.run_order(self.adapter(status=422))
        self.assertEqual(log.status,"Failed")
        self.assertNotIn("linked",calls)

    def test_ui_success_returns_provider_message_and_log_reference(self):
        adapter=self.adapter()
        adapter.send.return_value=(doc(status_code=201),{
            "success":True,"message":"Order created successfully",
            "result":{"id":"NEW-1","status":"New"},"traceId":"trace-1"},"NEW-1")
        result,log,calls=self.run_order(adapter,ui_mode=1)
        self.assertTrue(result["success"])
        self.assertEqual(result["outcome"],"created")
        self.assertEqual(result["message"],"Order created successfully")
        self.assertEqual(result["sync_log"],"LOG-TEST")
        self.assertEqual(result["provider_trace_id"],"trace-1")

    def test_ui_rejection_is_retryable_but_uncertain_is_not(self):
        rejected=self.adapter(status=422)
        rejected.send.return_value=(doc(status_code=422),{
            "message":"Invalid postal code",
            "errors":[{"message":"Postal code is required"}]},None)
        result,log,calls=self.run_order(rejected,ui_mode=1)
        self.assertEqual(result["outcome"],"provider_rejected")
        self.assertTrue(result["retry_allowed"])
        self.assertEqual(result["message"],"Invalid postal code")
        uncertain,log,calls=self.run_order(self.adapter(status=503),ui_mode=1)
        self.assertEqual(uncertain["outcome"],"uncertain")
        self.assertFalse(uncertain["retry_allowed"])

    def test_local_failure_after_creation_blocks_resending(self):
        result,log,calls=self.run_order(self.adapter(),persist_error=True)
        self.assertEqual(log.status,"Uncertain")
        self.assertEqual(log.shipkia_order_id,"NEW-1")
    def test_ui_local_save_failure_never_allows_resend(self):
        result,log,calls=self.run_order(self.adapter(),persist_error=True,ui_mode=1)
        self.assertEqual(result["outcome"],"local_save_failed")
        self.assertEqual(result["order_id"],"NEW-1")
        self.assertFalse(result["retry_allowed"])
        self.assertEqual(log.status,"Uncertain")


    def test_replacement_requires_reason(self):
        adapter=self.adapter()
        result,log,calls=self.run_order(adapter,previous=True)
        self.assertIsInstance(result,frappe.ValidationError)
        adapter.send.assert_not_called()

    def test_replacement_keeps_original_account(self):
        result,log,calls=self.run_order(self.adapter(),previous=True,reason="Replace cancelled order")
        self.assertEqual(result["order_id"],"NEW-1")

    def test_dispatch_routes_new_orders_to_selected_default(self):
        from shipment_tracking.api import dispatch
        invoice = doc(name="INV-TEST",check_permission=Mock(),si_shipkia_shipment=None)
        with patch.object(frappe,"get_doc",return_value=invoice), patch.object(dispatch,"get_account",return_value=doc(name="New OMS",platform="New OMS")), patch.object(orders,"run",return_value={}) as run:
            dispatch.create_order_for_sales_invoice("INV-TEST",confirmed_account="New OMS")
        self.assertEqual(run.call_args.args[1],"New OMS")
        self.assertIs(run.call_args.args[2],v2)

    def test_order_context_describes_all_payment_modes(self):
        from shipment_tracking.api import dispatch
        cases = (
            (10800, 10800, "Cash on Delivery", 0),
            (10800, 6800, "Partial Payment + COD", 4000),
            (10800, 0, "Prepaid", 10800),
        )
        for total, outstanding, payment, paid in cases:
            with self.subTest(payment=payment):
                invoice = doc(check_permission=Mock(), si_shipkia_shipment=None,
                              grand_total=total, outstanding_amount=outstanding, currency="INR")
                account = doc(name="New OMS", platform="New OMS")
                with patch.object(frappe, "get_doc", return_value=invoice), \
                     patch.object(dispatch, "get_account", return_value=account):
                    context = dispatch.get_order_context("INV-TEST")
                self.assertEqual(context["invoice_total"], total)
                self.assertEqual(context["outstanding"], outstanding)
                self.assertEqual(context["payment"], payment)
                self.assertEqual(context["paid"], paid)
    def test_default_change_after_confirmation_blocks_send(self):
        from shipment_tracking.api import dispatch
        with patch.object(frappe,"get_doc",return_value=doc(check_permission=Mock())), patch.object(dispatch,"get_account",return_value=doc(name="Legacy",platform="Legacy")), patch.object(orders,"run") as run:
            with self.assertRaises(frappe.ValidationError):
                dispatch.create_order_for_sales_invoice("INV-TEST",confirmed_account="New OMS")
        run.assert_not_called()
    def test_ui_mode_returns_local_validation_without_sending(self):
        from shipment_tracking.api import dispatch
        invoice=doc(check_permission=Mock(),si_shipkia_shipment=None)
        account=doc(name="New OMS",platform="New OMS")
        with patch.object(frappe,"get_doc",return_value=invoice), \
             patch.object(dispatch,"get_account",return_value=account), \
             patch.object(orders,"run",side_effect=frappe.ValidationError("Mobile number is missing")):
            result=dispatch.create_order_for_sales_invoice(
                "INV-TEST",confirmed_account="New OMS",ui_mode=1)
        self.assertEqual(result["outcome"],"local_validation_failed")
        self.assertFalse(result["request_sent"])
        self.assertTrue(result["retry_allowed"])


    def test_legacy_tracking_cannot_use_v2_account(self):
        from shipment_tracking.api import accounts
        with patch.object(accounts,"get_account",return_value=doc(name="New OMS",platform="New OMS")), patch.object(accounts,"reference_account",return_value="New OMS"):
            with self.assertRaises(frappe.ValidationError):
                accounts.legacy_settings(doc())

    def test_old_shipment_update_cannot_replace_current_summary(self):
        from shipment_tracking.api import tracking
        shipment = doc(name="OLD",shipkia_order_id="OLD-ORDER",shipkia_awb_number="OLD-AWB",
                       delivery_partner=None,courier_partner_mode=None,shipkia_stage=None,shipkia_status="Delivered",
                       shipkia_estimated_delivery=None,shipkia_delivered_on=None)
        with patch.object(frappe.db,"get_value",return_value="NEW"), patch("shipment_tracking.services.shipments.update_doc_if_exists") as update:
            tracking.mirror_summary_fields(shipment,"INV-TEST","ENC-TEST")
        update.assert_not_called()

    def test_current_shipment_mirrors_courier_mode_to_invoice_and_encounter(self):
        from shipment_tracking.api import tracking
        shipment = doc(name="SHIP-TEST", shipkia_order_id="ORD-1", shipkia_awb_number="AWB-1",
                       delivery_partner="Delhivery", courier_partner_mode="Delhivery Express",
                       shipkia_stage="Ready", shipkia_status="Pickup Scheduled",
                       shipkia_estimated_delivery=None, shipkia_delivered_on=None)
        with patch.object(frappe.db, "get_value", return_value="SHIP-TEST"), \
             patch("shipment_tracking.services.shipments.update_doc_if_exists") as update:
            tracking.mirror_summary_fields(shipment, "INV-TEST", "ENC-TEST")
        invoice_values = update.call_args_list[0].args[2]
        encounter_values = update.call_args_list[1].args[2]
        self.assertEqual(invoice_values["si_courier_partner_mode"], "Delhivery Express")
        self.assertEqual(encounter_values["pe_courier_partner_mode"], "Delhivery Express")
    def test_tracking_router_selects_v2_adapter(self):
        from shipment_tracking.api import tracking
        account = doc(name="New OMS", platform="New OMS")
        adapter = tracking._adapter_for(account)
        self.assertEqual(adapter.__name__, "shipment_tracking.api.v2.tracking")
    def test_legacy_shipment_uses_default_new_oms_tracking_gateway(self):
        from shipment_tracking.api import tracking

        shipment = doc(shipkia_account="Legacy")
        gateway = doc(name="New OMS", platform="New OMS")
        settings = doc(default_shipkia_account="New OMS")
        with (
            patch.object(frappe, "get_single", return_value=settings),
            patch.object(tracking, "get_account", return_value=gateway) as get_account,
        ):
            account = tracking._tracking_account_for_shipment(shipment)

        self.assertIs(account, gateway)
        get_account.assert_called_once_with("New OMS")

    def test_legacy_shipment_sync_uses_v2_adapter(self):
        from shipment_tracking.api import tracking
        from shipment_tracking.api.v2 import tracking as v2_tracking
        from shipment_tracking.services import tracking as tracking_service

        shipment = doc(shipkia_account="Legacy")
        gateway = doc(
            name="New OMS",
            platform="New OMS",
            allow_existing_operations=1,
            enable_manual_tracking_refresh=1,
            order_tracking_url="https://api.shipkia.com/tracking",
        )
        with (
            patch.object(tracking, "_tracking_account_for_shipment", return_value=gateway),
            patch.object(tracking_service, "run", return_value={"success": True}) as run,
        ):
            result = tracking._sync_tracking(shipment)

        self.assertTrue(result["success"])
        run.assert_called_once_with(shipment, gateway, v2_tracking)
