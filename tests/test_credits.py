"""Tests for the credits service, ported from credits_test.go."""

import json
import unittest

from invoice_ninja import Client, Credit, CreditListOptions, LineItem

from .support import TestServer


def _json(payload):
    return json.dumps(payload).encode("utf-8")


class TestCreditsService(unittest.TestCase):
    def test_list(self):
        def callback(request):
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.path, "/api/v1/credits")
            self.assertEqual(request.query_get("client_id"), "client123")
            return (
                200,
                {},
                _json({"data": [{"id": "cr1"}, {"id": "cr2"}], "meta": {"pagination": {"total": 2}}}),
            )

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        resp = client.credits.list(CreditListOptions(client_id="client123"))
        self.assertEqual(len(resp.data), 2)

    def test_get(self):
        server = TestServer(lambda request: (200, {}, _json({"data": {"id": "cr1", "amount": 50.0}})))
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        credit = client.credits.get("cr1")
        self.assertEqual(credit.id, "cr1")
        self.assertEqual(credit.amount, 50.0)

    def test_create(self):
        def callback(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.path, "/api/v1/credits")
            body = json.loads(request.body.decode("utf-8"))
            self.assertEqual(body["client_id"], "client123")
            self.assertEqual(body["line_items"][0]["cost"], 100.0)
            return 200, {}, _json({"data": {"id": "newcr"}})

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        credit = client.credits.create(
            Credit(client_id="client123", line_items=[LineItem(product_key="Credit", quantity=1, cost=100.0)])
        )
        self.assertEqual(credit.id, "newcr")

    def test_update(self):
        def callback(request):
            self.assertEqual(request.method, "PUT")
            self.assertEqual(request.path, "/api/v1/credits/cr1")
            return 200, {}, _json({"data": {"id": "cr1", "public_notes": "Updated"}})

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        credit = client.credits.update("cr1", Credit(public_notes="Updated"))
        self.assertEqual(credit.id, "cr1")

    def test_delete(self):
        def callback(request):
            self.assertEqual(request.method, "DELETE")
            self.assertEqual(request.path, "/api/v1/credits/cr1")
            return 200, {}, b""

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        client.credits.delete("cr1")

    def test_bulk(self):
        def callback(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.path, "/api/v1/credits/bulk")
            body = json.loads(request.body.decode("utf-8"))
            self.assertEqual(body["action"], "archive")
            return 200, {}, _json({"data": [{"id": "cr1"}, {"id": "cr2"}]})

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        credits = client.credits.bulk("archive", ["cr1", "cr2"])
        self.assertEqual(len(credits), 2)

    def test_mark_sent_and_email(self):
        for method, action in (("mark_sent", "mark_sent"), ("email", "email"),
                               ("archive", "archive"), ("restore", "restore")):
            with self.subTest(method=method):
                seen = {}

                def callback(request):
                    body = json.loads(request.body.decode("utf-8"))
                    seen["action"] = body["action"]
                    return 200, {}, _json({"data": [{"id": "cr1"}]})

                server = TestServer(callback)
                self.addCleanup(server.close)

                client = Client("test-token", base_url=server.url)
                credit = getattr(client.credits, method)("cr1")
                self.assertEqual(credit.id, "cr1")
                self.assertEqual(seen["action"], action)

    def test_get_blank(self):
        server = TestServer(lambda request: (200, {}, _json({"data": {"id": ""}})))
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        credit = client.credits.get_blank()
        self.assertEqual(credit.id, "")


class TestCreditListOptions(unittest.TestCase):
    def test_to_query(self):
        opts = CreditListOptions(
            per_page=20,
            page=1,
            filter="test",
            client_id="client123",
            status="active",
            is_deleted=True,
            sort="amount|desc",
            include="invoices",
        )

        q = opts.to_query()

        self.assertEqual(q["per_page"], ["20"])
        self.assertEqual(q["client_id"], ["client123"])
        self.assertEqual(q["is_deleted"], ["true"])
        self.assertEqual(q["sort"], ["amount|desc"])

    def test_to_query_omits_unset_fields(self):
        self.assertEqual(CreditListOptions().to_query(), {})


if __name__ == "__main__":
    unittest.main()
