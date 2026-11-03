"""Tests for the invoices service, ported from invoices_test.go."""

import json
import unittest

from invoice_ninja import Client, Invoice, InvoiceListOptions, LineItem

from .support import TestServer


def _json(payload):
    return json.dumps(payload).encode("utf-8")


class TestInvoicesService(unittest.TestCase):
    def test_list(self):
        def callback(request):
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.path, "/api/v1/invoices")
            self.assertEqual(request.query_get("per_page"), "10")
            self.assertEqual(request.query_get("client_id"), "client123")
            return (
                200,
                {},
                _json(
                    {
                        "data": [{"id": "inv1"}, {"id": "inv2"}],
                        "meta": {"pagination": {"total": 2, "count": 2, "per_page": 10,
                                                "current_page": 1, "total_pages": 1}},
                    }
                ),
            )

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        resp = client.invoices.list(InvoiceListOptions(per_page=10, client_id="client123"))

        self.assertEqual(len(resp.data), 2)
        self.assertEqual(resp.meta.pagination.total, 2)

    def test_get(self):
        def callback(request):
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.path, "/api/v1/invoices/inv123")
            return 200, {}, _json({"data": {"id": "inv123", "number": "INV001", "amount": 500.0}})

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        invoice = client.invoices.get("inv123")
        self.assertEqual(invoice.id, "inv123")
        self.assertEqual(invoice.amount, 500.0)

    def test_create(self):
        def callback(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.path, "/api/v1/invoices")
            body = json.loads(request.body.decode("utf-8"))
            self.assertEqual(body["client_id"], "client123")
            self.assertEqual(body["line_items"][0]["product_key"], "Product A")
            self.assertEqual(body["line_items"][0]["quantity"], 2)
            self.assertEqual(body["line_items"][0]["cost"], 50.0)
            return 200, {}, _json({"data": {"id": "new123", "number": "INV002"}})

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        invoice = client.invoices.create(
            Invoice(client_id="client123", line_items=[LineItem(product_key="Product A", quantity=2, cost=50.0)])
        )
        self.assertEqual(invoice.id, "new123")

    def test_update(self):
        def callback(request):
            self.assertEqual(request.method, "PUT")
            self.assertEqual(request.path, "/api/v1/invoices/inv123")
            return 200, {}, _json({"data": {"id": "inv123", "public_notes": "Updated"}})

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        invoice = client.invoices.update("inv123", Invoice(public_notes="Updated"))
        self.assertEqual(invoice.id, "inv123")

    def test_delete(self):
        def callback(request):
            self.assertEqual(request.method, "DELETE")
            self.assertEqual(request.path, "/api/v1/invoices/inv123")
            return 200, {}, b""

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        client.invoices.delete("inv123")

    def test_bulk(self):
        def callback(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.path, "/api/v1/invoices/bulk")
            body = json.loads(request.body.decode("utf-8"))
            self.assertEqual(body["action"], "mark_sent")
            return 200, {}, _json({"data": [{"id": "inv1"}, {"id": "inv2"}]})

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        invoices = client.invoices.bulk("mark_sent", ["inv1", "inv2"])
        self.assertEqual(len(invoices), 2)

    def test_mark_paid(self):
        def callback(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.path, "/api/v1/invoices/bulk")
            body = json.loads(request.body.decode("utf-8"))
            self.assertEqual(body["action"], "mark_paid")
            self.assertEqual(body["ids"], ["inv123"])
            return 200, {}, _json({"data": [{"id": "inv123", "status_id": "4"}]})

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        invoice = client.invoices.mark_paid("inv123")
        self.assertEqual(invoice.id, "inv123")

    def test_archive_restore_mark_sent_email(self):
        for action, method in (
            ("archive", "archive"),
            ("restore", "restore"),
            ("mark_sent", "mark_sent"),
            ("email", "email"),
        ):
            with self.subTest(action=action):
                server = TestServer(
                    lambda request, action=action: (
                        200,
                        {},
                        _json({"data": [{"id": "inv123"}]}),
                    )
                )
                self.addCleanup(server.close)

                client = Client("test-token", base_url=server.url)
                invoice = getattr(client.invoices, method)("inv123")
                self.assertEqual(invoice.id, "inv123")

    def test_get_blank(self):
        server = TestServer(lambda request: (200, {}, _json({"data": {"id": ""}})))
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        invoice = client.invoices.get_blank()
        self.assertEqual(invoice.id, "")

    def test_download(self):
        expected_pdf = b"%PDF-1.4 fake invoice pdf content"

        def callback(request):
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.path, "/api/v1/invoice/inv-key-123/download")
            self.assertEqual(request.header("Accept"), "application/pdf")
            return 200, {"Content-Type": "application/pdf"}, expected_pdf

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        pdf = client.invoices.download("inv-key-123")
        self.assertEqual(pdf, expected_pdf)


class TestInvoiceListOptions(unittest.TestCase):
    def test_to_query(self):
        opts = InvoiceListOptions(
            per_page=10,
            page=2,
            filter="test",
            client_id="client123",
            status="active",
            created_at="2024-01-01",
            updated_at="2024-01-15",
            is_deleted=False,
            sort="id|desc",
            include="payments",
        )

        q = opts.to_query()

        self.assertEqual(q["per_page"], ["10"])
        self.assertEqual(q["page"], ["2"])
        self.assertEqual(q["filter"], ["test"])
        self.assertEqual(q["client_id"], ["client123"])
        self.assertEqual(q["status"], ["active"])
        self.assertEqual(q["is_deleted"], ["false"])
        self.assertEqual(q["sort"], ["id|desc"])
        self.assertEqual(q["include"], ["payments"])

    def test_to_query_omits_unset_fields(self):
        q = InvoiceListOptions().to_query()
        self.assertEqual(q, {})


class TestInvoiceJSON(unittest.TestCase):
    def test_discount_and_inclusive_taxes_json(self):
        invoice = Invoice.from_dict(
            {"id": "inv123", "discount": 10.5, "uses_inclusive_taxes": True}
        )
        self.assertEqual(invoice.discount, 10.5)
        self.assertTrue(invoice.uses_inclusive_taxes)

        encoded = Invoice(client_id="client123", discount=5, uses_inclusive_taxes=True).to_dict()
        self.assertEqual(encoded["discount"], 5)
        self.assertTrue(encoded["uses_inclusive_taxes"])

    def test_zero_values_omitted(self):
        encoded = Invoice(id="inv1").to_dict()
        self.assertEqual(encoded, {"id": "inv1"})

    def test_line_items_round_trip(self):
        invoice = Invoice.from_dict(
            {
                "id": "inv1",
                "line_items": [
                    {"product_key": "A", "quantity": 2, "cost": 10.5},
                    {"product_key": "B", "quantity": 1, "cost": 5},
                ],
            }
        )
        self.assertEqual(len(invoice.line_items), 2)
        self.assertEqual(invoice.line_items[0].product_key, "A")
        self.assertEqual(invoice.line_items[1].cost, 5.0)

        encoded = invoice.to_dict()
        self.assertEqual(encoded["line_items"][0]["quantity"], 2.0)


if __name__ == "__main__":
    unittest.main()
