from unittest import TestCase

from shipment_tracking.services.order_results import (
    local_validation,
    provider_summary,
    result,
    safe_text,
)


class TestOrderResults(TestCase):
    def test_provider_summary_extracts_safe_messages_and_trace(self):
        summary = provider_summary(
            {
                "message": "<b>Invalid order</b>",
                "errors": [{"message": "Postal code is required"}],
                "traceId": "trace-123",
                "api_key": "must-not-be-returned",
            },
            "Rejected",
        )
        self.assertEqual(summary["message"], "Invalid order")
        self.assertEqual(summary["validation_messages"], ["Postal code is required"])
        self.assertEqual(summary["provider_trace_id"], "trace-123")
        self.assertNotIn("must-not-be-returned", str(summary))

    def test_result_has_stable_shape_and_escapes_untrusted_markup(self):
        output = result(
            "provider_rejected",
            "<script>Rejected</script>",
            "<img src=x onerror=alert(1)> Bad request",
            validation_messages=["<b>Bad postal code</b>"],
        )
        self.assertEqual(output["title"], "Rejected")
        self.assertEqual(output["message"], "Bad request")
        self.assertEqual(output["validation_messages"], ["Bad postal code"])
        self.assertFalse(output["success"])

    def test_local_validation_was_not_sent_and_is_retryable(self):
        output = local_validation("Mobile number is missing")
        self.assertEqual(output["outcome"], "local_validation_failed")
        self.assertFalse(output["request_sent"])
        self.assertTrue(output["retry_allowed"])

    def test_safe_text_is_bounded(self):
        self.assertEqual(len(safe_text("x" * 700)), 500)
