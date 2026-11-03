"""Tests for the payments service, ported from payments_test.go."""

import json
import unittest

from invoice_ninja import Client, PaymentInvoice, PaymentListOptions, PaymentRequest, RefundRequest

from .support import TestServer


def _json(payload):
    return json.dumps(payload).encode("utf-8")


class TestPaymentsService(unittest.TestCase):
    def test_list(self):
        def callback(request):
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.path, "/api/v1/payments")
            self.assertEqual(request.query_get("per_page"), "10")
            self.assertEqual(request.query_get("page"), "2")
            return (
                200,
                {"Content-Type": "application/json"},
                _json(
                    {
                        "data": [
                            {"id": "abc123", "amount": 100.00},
                            {"id": "def456", "amount": 200.00},
                        ],
                        "meta": {
                            "pagination": {
                                "total": 50,
                                "count": 2,
                                "per_page": 10,
                                "current_page": 2,
                                "total_pages": 5,
                            }
                        },
                    }
                ),
            )

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        resp = client.payments.list(PaymentListOptions(per_page=10, page=2))

        self.assertEqual(len(resp.data), 2)
        self.assertEqual(resp.data[0].id, "abc123")
        self.assertEqual(resp.meta.pagination.total, 50)

    def test_get(self):
        def callback(request):
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.path, "/api/v1/payments/abc123")
            return (
                200,
                {"Content-Type": "application/json"},
                _json({"data": {"id": "abc123", "amount": 100.0, "client_id": "client123",
                                "is_deleted": False}}),
            )

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        payment = client.payments.get("abc123")

        self.assertEqual(payment.id, "abc123")
        self.assertEqual(payment.amount, 100.0)

    def test_create(self):
        def callback(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.path, "/api/v1/payments")
            body = json.loads(request.body.decode("utf-8"))
            self.assertEqual(body["client_id"], "client123")
            self.assertEqual(body["amount"], 150.0)
            self.assertEqual(body["invoices"][0]["invoice_id"], "inv123")
            return (
                200,
                {"Content-Type": "application/json"},
                _json({"data": {"id": "new123", "client_id": "client123", "amount": 150.0}}),
            )

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        payment = client.payments.create(
            PaymentRequest(
                client_id="client123",
                amount=150.0,
                date="2024-01-15",
                invoices=[PaymentInvoice(invoice_id="inv123", amount=150.0)],
            )
        )

        self.assertEqual(payment.id, "new123")

    def test_create_with_email_receipt(self):
        def callback(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.query_get("email_receipt"), "true")
            return 200, {}, _json({"data": {"id": "new123"}})

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        payment = client.payments.create_with_email_receipt(
            PaymentRequest(client_id="client123", amount=10.0), True
        )
        self.assertEqual(payment.id, "new123")

    def test_update(self):
        def callback(request):
            self.assertEqual(request.method, "PUT")
            self.assertEqual(request.path, "/api/v1/payments/abc123")
            return 200, {}, _json({"data": {"id": "abc123", "private_notes": "Updated notes"}})

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        payment = client.payments.update("abc123", PaymentRequest(private_notes="Updated notes"))
        self.assertEqual(payment.id, "abc123")

    def test_delete(self):
        def callback(request):
            self.assertEqual(request.method, "DELETE")
            self.assertEqual(request.path, "/api/v1/payments/abc123")
            return 200, {}, b""

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        client.payments.delete("abc123")

    def test_refund(self):
        def callback(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.path, "/api/v1/payments/refund")
            return 200, {}, _json({"data": {"id": "abc123", "refunded": 50.0}})

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        payment = client.payments.refund(RefundRequest(id="abc123", amount=50.0))
        self.assertEqual(payment.refunded, 50.0)

    def test_bulk(self):
        def callback(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.path, "/api/v1/payments/bulk")
            body = json.loads(request.body.decode("utf-8"))
            self.assertEqual(body["action"], "archive")
            self.assertEqual(body["ids"], ["abc123", "def456"])
            return 200, {}, _json({"data": [{"id": "abc123"}, {"id": "def456"}]})

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        payments = client.payments.bulk("archive", ["abc123", "def456"])
        self.assertEqual(len(payments), 2)

    def test_archive_and_restore(self):
        for action, method in (("archive", "archive"), ("restore", "restore")):
            with self.subTest(action=action):
                server = TestServer(
                    lambda request, action=action: (
                        200,
                        {},
                        _json({"data": [{"id": "abc123"}]}),
                    )
                )
                self.addCleanup(server.close)

                client = Client("test-token", base_url=server.url)
                payment = getattr(client.payments, method)("abc123")
                self.assertEqual(payment.id, "abc123")

    def test_get_blank(self):
        server = TestServer(lambda request: (200, {}, _json({"data": {"id": "", "amount": 0}})))
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        payment = client.payments.get_blank()
        self.assertEqual(payment.id, "")


class TestPaymentListOptions(unittest.TestCase):
    def test_to_query(self):
        opts = PaymentListOptions(
            per_page=10,
            page=2,
            filter="test",
            number="PAY001",
            client_id="client123",
            status="active,archived",
            created_at="2024-01-01",
            updated_at="2024-01-15",
            is_deleted=True,
            vendor_id="vendor123",
            sort="amount|desc",
            include="invoices",
        )

        q = opts.to_query()

        self.assertEqual(q["per_page"], ["10"])
        self.assertEqual(q["page"], ["2"])
        self.assertEqual(q["filter"], ["test"])
        self.assertEqual(q["number"], ["PAY001"])
        self.assertEqual(q["client_id"], ["client123"])
        self.assertEqual(q["is_deleted"], ["true"])
        self.assertEqual(q["vendor_id"], ["vendor123"])
        self.assertEqual(q["sort"], ["amount|desc"])
        self.assertEqual(q["include"], ["invoices"])

    def test_to_query_false_is_deleted(self):
        opts = PaymentListOptions(is_deleted=False)
        self.assertEqual(opts.to_query()["is_deleted"], ["false"])

    def test_list_with_nil_options_sends_no_query(self):
        targets = []

        server = TestServer(lambda request: (targets.append(request.target), (200, {}, _json({"data": []})))[1])
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        client.payments.list(None)

        self.assertEqual(targets, ["/api/v1/payments"])


if __name__ == "__main__":
    unittest.main()
