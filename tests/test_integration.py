"""Integration tests against a live Invoice Ninja server, ported from
integration_test.go.

These tests are skipped by default. To run them:

    INVOICE_NINJA_RUN_INTEGRATION=1 python -m unittest tests.test_integration

against the demo server, or against a custom server:

    INVOICE_NINJA_BASE_URL=https://your-server.com \\
    INVOICE_NINJA_API_TOKEN=your-token \\
    INVOICE_NINJA_RUN_INTEGRATION=1 python -m unittest tests.test_integration
"""

import os
import unittest

from invoice_ninja import (
    APIError,
    DEMO_BASE_URL,
    Client,
    ClientListOptions,
    CreditListOptions,
    InvoiceListOptions,
    PaymentListOptions,
    PaymentTermListOptions,
    is_api_error,
)

RUN = os.environ.get("INVOICE_NINJA_RUN_INTEGRATION", "") == "1"


@unittest.skipUnless(RUN, "set INVOICE_NINJA_RUN_INTEGRATION=1 to run integration tests")
class TestIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base_url = os.environ.get("INVOICE_NINJA_BASE_URL") or DEMO_BASE_URL
        api_token = os.environ.get("INVOICE_NINJA_API_TOKEN") or "TOKEN"  # Demo API token
        cls.client = Client(api_token, base_url=base_url, timeout=30)

    def test_list_payments(self):
        payments = self.client.payments.list(PaymentListOptions(per_page=5, page=1))
        print(f"Found {len(payments.data)} payments (page 1)")
        for payment in payments.data:
            print(f"  Payment {payment.number}: ${payment.amount:.2f}")

    def test_list_invoices(self):
        invoices = self.client.invoices.list(InvoiceListOptions(per_page=5, page=1))
        print(f"Found {len(invoices.data)} invoices (page 1)")

    def test_list_clients(self):
        clients = self.client.clients.list(ClientListOptions(per_page=5, page=1))
        print(f"Found {len(clients.data)} clients (page 1)")

    def test_list_payment_terms(self):
        terms = self.client.payment_terms.list(PaymentTermListOptions(per_page=5, page=1))
        print(f"Found {len(terms.data)} payment terms (page 1)")

    def test_list_credits(self):
        credits = self.client.credits.list(CreditListOptions(per_page=5, page=1))
        print(f"Found {len(credits.data)} credits (page 1)")

    def test_get_payment(self):
        payments = self.client.payments.list(PaymentListOptions(per_page=1))
        if not payments.data:
            self.skipTest("no payments on the server")
        payment = self.client.payments.get(payments.data[0].id)
        self.assertEqual(payment.id, payments.data[0].id)

    def test_get_invoice(self):
        invoices = self.client.invoices.list(InvoiceListOptions(per_page=1))
        if not invoices.data:
            self.skipTest("no invoices on the server")
        invoice = self.client.invoices.get(invoices.data[0].id)
        self.assertEqual(invoice.id, invoices.data[0].id)

    def test_get_client(self):
        clients = self.client.clients.list(ClientListOptions(per_page=1))
        if not clients.data:
            self.skipTest("no clients on the server")
        client = self.client.clients.get(clients.data[0].id)
        self.assertEqual(client.id, clients.data[0].id)

    def test_pagination(self):
        first = self.client.clients.list(ClientListOptions(per_page=2, page=1))
        if not first.data:
            self.skipTest("no clients on the server")
        if (first.meta.pagination.total_pages or 1) >= 2:
            second = self.client.clients.list(ClientListOptions(per_page=2, page=2))
            self.assertEqual(second.meta.pagination.current_page, 2)

    def test_generic_request(self):
        result = self.client.request("GET", "/api/v1/activities")
        self.assertIsNotNone(result)

    def test_error_handling(self):
        with self.assertRaises(APIError) as ctx:
            self.client.payments.get("invalid-id-404")
        api_err = is_api_error(ctx.exception)
        self.assertIsNotNone(api_err)

    def test_filtering(self):
        payments = self.client.payments.list(
            PaymentListOptions(per_page=5, status="active")
        )
        self.assertIsNotNone(payments.data)


if __name__ == "__main__":
    unittest.main()
