"""Tests for the payment terms service, ported from payment_terms_test.go."""

import json
import unittest

from invoice_ninja import Client, PaymentTerm, PaymentTermListOptions

from .support import TestServer


def _json(payload):
    return json.dumps(payload).encode("utf-8")


class TestPaymentTermsService(unittest.TestCase):
    def test_list(self):
        def callback(request):
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.path, "/api/v1/payment_terms")
            self.assertEqual(request.query_get("per_page"), "10")
            return (
                200,
                {},
                _json({"data": [{"id": "t1", "name": "Net 30"}, {"id": "t2", "name": "Net 60"}]}),
            )

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        resp = client.payment_terms.list(PaymentTermListOptions(per_page=10))
        self.assertEqual(len(resp.data), 2)
        self.assertEqual(resp.data[0].name, "Net 30")

    def test_list_with_nil_options(self):
        server = TestServer(lambda request: (200, {}, _json({"data": []})))
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        resp = client.payment_terms.list(None)
        self.assertEqual(resp.data, [])

    def test_get(self):
        server = TestServer(lambda request: (200, {}, _json({"data": {"id": "t1", "num_days": 30}})))
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        term = client.payment_terms.get("t1")
        self.assertEqual(term.id, "t1")
        self.assertEqual(term.num_days, 30)

    def test_create(self):
        def callback(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.path, "/api/v1/payment_terms")
            body = json.loads(request.body.decode("utf-8"))
            self.assertEqual(body["name"], "Net 45")
            self.assertEqual(body["num_days"], 45)
            return 200, {}, _json({"data": {"id": "new45", "name": "Net 45", "num_days": 45}})

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        term = client.payment_terms.create(PaymentTerm(name="Net 45", num_days=45))
        self.assertEqual(term.id, "new45")

    def test_update(self):
        def callback(request):
            self.assertEqual(request.method, "PUT")
            self.assertEqual(request.path, "/api/v1/payment_terms/t1")
            return 200, {}, _json({"data": {"id": "t1", "name": "Net 60"}})

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        term = client.payment_terms.update("t1", PaymentTerm(name="Net 60"))
        self.assertEqual(term.name, "Net 60")

    def test_delete(self):
        def callback(request):
            self.assertEqual(request.method, "DELETE")
            self.assertEqual(request.path, "/api/v1/payment_terms/t1")
            return 200, {}, b""

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        client.payment_terms.delete("t1")

    def test_archive_and_restore(self):
        for method in ("archive", "restore"):
            with self.subTest(method=method):
                server = TestServer(lambda request: (200, {}, _json({"data": [{"id": "t1"}]})))
                self.addCleanup(server.close)

                client = Client("test-token", base_url=server.url)
                term = getattr(client.payment_terms, method)("t1")
                self.assertEqual(term.id, "t1")

    def test_get_blank(self):
        server = TestServer(lambda request: (200, {}, _json({"data": {"id": ""}})))
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        term = client.payment_terms.get_blank()
        self.assertEqual(term.id, "")


class TestPaymentTermListOptions(unittest.TestCase):
    def test_to_query(self):
        opts = PaymentTermListOptions(per_page=10, page=2, include="x")
        q = opts.to_query()
        self.assertEqual(q["per_page"], ["10"])
        self.assertEqual(q["page"], ["2"])
        self.assertEqual(q["include"], ["x"])

    def test_to_query_omits_unset_fields(self):
        self.assertEqual(PaymentTermListOptions().to_query(), {})


if __name__ == "__main__":
    unittest.main()
