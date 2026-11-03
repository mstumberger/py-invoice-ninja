"""Tests for model (de)serialization, ported from the Go model behaviour and
the testdata fixtures used by example/integration tests."""

import json
import os
import unittest

from invoice_ninja import (
    BulkAction,
    ClientContact,
    INClient,
    Payment,
    Paymentable,
    PaymentRequest,
    PaymentInvoice,
    RefundRequest,
    StatementRequest,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "testdata")


class TestSerialization(unittest.TestCase):
    def test_payment_fixture_round_trip(self):
        with open(os.path.join(FIXTURES, "payment.json")) as handle:
            payload = json.load(handle)

        payment = Payment.from_dict(payload["data"])

        self.assertEqual(payment.id, "test-payment-id")
        self.assertEqual(payment.client_id, "test-client-id")
        self.assertEqual(payment.number, "0001")
        self.assertEqual(payment.amount, 250.0)
        self.assertEqual(payment.date, "2024-01-15")
        self.assertEqual(payment.transaction_ref, "TXN-12345")
        self.assertEqual(payment.private_notes, "Test payment")
        self.assertFalse(payment.is_deleted)
        self.assertEqual(payment.updated_at, 1705305600)

        encoded = payment.to_dict()
        self.assertEqual(encoded["transaction_reference"], "TXN-12345")
        self.assertEqual(encoded["updated_at"], 1705305600)

    def test_payments_list_fixture(self):
        with open(os.path.join(FIXTURES, "payments_list.json")) as handle:
            payload = json.load(handle)

        payments = [Payment.from_dict(item) for item in payload["data"]]
        self.assertTrue(len(payments) >= 1)

    def test_omitempty_drops_zero_values(self):
        payment = Payment()
        self.assertEqual(payment.to_dict(), {})

        payment = Payment(id="p1", amount=0, is_manual=False, is_deleted=False)
        self.assertEqual(payment.to_dict(), {"id": "p1"})

    def test_false_serialized_when_required(self):
        request = RefundRequest(id="p1")
        encoded = request.to_dict()
        # "id" has no omitempty in Go.
        self.assertEqual(encoded["id"], "p1")
        self.assertNotIn("amount", encoded)

    def test_bulk_action_always_serializes(self):
        self.assertEqual(BulkAction().to_dict(), {"action": "", "ids": []})
        self.assertEqual(
            BulkAction(action="archive", ids=["a"]).to_dict(),
            {"action": "archive", "ids": ["a"]},
        )

    def test_statement_request_client_id_required(self):
        self.assertEqual(StatementRequest().to_dict(), {"client_id": ""})

    def test_payment_request_nested(self):
        request = PaymentRequest(
            client_id="c1",
            amount=100.0,
            invoices=[PaymentInvoice(invoice_id="i1", amount=100.0)],
        )
        encoded = request.to_dict()
        self.assertEqual(
            encoded,
            {"client_id": "c1", "amount": 100.0, "invoices": [{"invoice_id": "i1", "amount": 100.0}]},
        )

        # Round trip through from_dict.
        parsed = PaymentRequest.from_dict(encoded)
        self.assertEqual(parsed.invoices[0].invoice_id, "i1")
        self.assertEqual(parsed.invoices[0].amount, 100.0)

    def test_payment_nested_paymentables(self):
        payment = Payment.from_dict(
            {
                "id": "p1",
                "paymentables": [
                    {"id": "pb1", "invoice_id": "i1", "amount": 50.0, "refunded": 10.0},
                    {"id": "pb2", "credit_id": "c1", "amount": 25.0},
                ],
            }
        )
        self.assertEqual(len(payment.paymentables), 2)
        self.assertIsInstance(payment.paymentables[0], Paymentable)
        self.assertEqual(payment.paymentables[0].invoice_id, "i1")
        self.assertEqual(payment.paymentables[1].credit_id, "c1")

    def test_client_contacts(self):
        client = INClient.from_dict(
            {
                "id": "c1",
                "name": "Acme",
                "shipping_postal_code": "1000",
                "shipping_country_id": "840",
                "contacts": [{"id": "ct1", "is_primary": 1}],
            }
        )
        self.assertEqual(client.shipping_postal, "1000")
        self.assertEqual(client.shipping_country, "840")
        self.assertIsInstance(client.contacts[0], ClientContact)
        self.assertTrue(client.contacts[0].is_primary)

        encoded = client.to_dict()
        self.assertEqual(encoded["shipping_postal_code"], "1000")
        self.assertEqual(encoded["shipping_country_id"], "840")

    def test_unknown_fields_ignored(self):
        payment = Payment.from_dict({"id": "p1", "mystery": True, "nested": {"x": 1}})
        self.assertEqual(payment.id, "p1")

    def test_numeric_coercion(self):
        payment = Payment.from_dict({"id": "p1", "amount": 100, "updated_at": 1705305600})
        self.assertEqual(payment.amount, 100.0)
        self.assertIsInstance(payment.amount, float)
        self.assertIsInstance(payment.updated_at, int)

    def test_invalid_field_type_raises(self):
        with self.assertRaises(ValueError):
            Payment.from_dict({"amount": "not-a-number"})


if __name__ == "__main__":
    unittest.main()
