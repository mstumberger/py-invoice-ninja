"""Tests for the clients service, ported from clients_test.go."""

import json
import unittest

from invoice_ninja import Client, ClientListOptions, INClient, ClientContact, StatementRequest

from .support import TestServer


def _json(payload):
    return json.dumps(payload).encode("utf-8")


def _client_with_contacts_payload(contacts):
    return {"data": {"id": "client123", "name": "Test Client", "contacts": contacts}}


class TestClientsService(unittest.TestCase):
    def test_list(self):
        def callback(request):
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.path, "/api/v1/clients")
            self.assertEqual(request.query_get("balance"), "gt:1000")
            self.assertEqual(request.query_get("include"), "contacts")
            return (
                200,
                {},
                _json(
                    {
                        "data": [{"id": "c1", "name": "Acme"}, {"id": "c2", "name": "Beta"}],
                        "meta": {"pagination": {"total": 2}},
                    }
                ),
            )

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        resp = client.clients.list(
            ClientListOptions(balance="gt:1000", include="contacts")
        )
        self.assertEqual(len(resp.data), 2)
        self.assertEqual(resp.data[0].name, "Acme")

    def test_get(self):
        def callback(request):
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.path, "/api/v1/clients/client123")
            return 200, {}, _json(
                {
                    "data": {
                        "id": "client123",
                        "name": "Test Client",
                        "contacts": [{"id": "contact1", "email": "john@example.com"}],
                    }
                }
            )

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        result = client.clients.get("client123")
        self.assertEqual(result.id, "client123")
        self.assertEqual(len(result.contacts), 1)
        self.assertEqual(result.contacts[0].email, "john@example.com")

    def test_create(self):
        def callback(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.path, "/api/v1/clients")
            body = json.loads(request.body.decode("utf-8"))
            self.assertEqual(body["name"], "Test Client")
            self.assertEqual(body["contacts"][0]["first_name"], "John")
            self.assertTrue(body["contacts"][0]["is_primary"])
            return 200, {}, _json({"data": {"id": "new123", "name": "Test Client"}})

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        result = client.clients.create(
            INClient(
                name="Test Client",
                contacts=[
                    ClientContact(first_name="John", last_name="Doe",
                                  email="john@example.com", is_primary=True)
                ],
            )
        )
        self.assertEqual(result.id, "new123")

    def test_update(self):
        def callback(request):
            self.assertEqual(request.method, "PUT")
            self.assertEqual(request.path, "/api/v1/clients/client123")
            return 200, {}, _json({"data": {"id": "client123", "name": "Renamed"}})

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        result = client.clients.update("client123", INClient(name="Renamed"))
        self.assertEqual(result.name, "Renamed")

    def test_delete(self):
        def callback(request):
            self.assertEqual(request.method, "DELETE")
            self.assertEqual(request.path, "/api/v1/clients/client123")
            return 200, {}, b""

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        client.clients.delete("client123")

    def test_purge(self):
        def callback(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.path, "/api/v1/clients/client123/purge")
            return 200, {}, b""

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        client.clients.purge("client123")

    def test_merge(self):
        def callback(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.path, "/api/v1/clients/primary/mergeable/merge")
            return 200, {}, _json({"data": {"id": "primary", "name": "Merged"}})

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        result = client.clients.merge("primary", "mergeable")
        self.assertEqual(result.id, "primary")

    def test_bulk(self):
        def callback(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.path, "/api/v1/clients/bulk")
            body = json.loads(request.body.decode("utf-8"))
            self.assertEqual(body["action"], "archive")
            return 200, {}, _json({"data": [{"id": "c1"}, {"id": "c2"}]})

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        result = client.clients.bulk("archive", ["c1", "c2"])
        self.assertEqual(len(result), 2)

    def test_archive_restore(self):
        for method in ("archive", "restore"):
            with self.subTest(method=method):
                server = TestServer(lambda request: (200, {}, _json({"data": [{"id": "c1"}]})))
                self.addCleanup(server.close)

                client = Client("test-token", base_url=server.url)
                result = getattr(client.clients, method)("c1")
                self.assertEqual(result.id, "c1")

    def test_get_blank(self):
        server = TestServer(lambda request: (200, {}, _json({"data": {"id": ""}})))
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        result = client.clients.get_blank()
        self.assertEqual(result.id, "")

    def test_get_statement_not_implemented(self):
        client = Client("test-token")
        with self.assertRaises(NotImplementedError) as ctx:
            client.clients.get_statement(StatementRequest(client_id="c1"))
        self.assertEqual(
            str(ctx.exception),
            "not implemented - use client.Request with custom handling",
        )


class TestClientPortal(unittest.TestCase):
    def _server_with_contacts(self, contacts):
        payload = _client_with_contacts_payload(contacts)
        server = TestServer(lambda request: (200, {}, _json(payload)))
        self.addCleanup(server.close)
        return server

    def test_switch_to_client_portal(self):
        server = self._server_with_contacts(
            [
                {
                    "id": "contact1",
                    "first_name": "John",
                    "last_name": "Doe",
                    "email": "john@example.com",
                    "is_primary": True,
                    "contact_key": "abc123xyz",
                }
            ]
        )
        client = Client("test-token", base_url=server.url)

        resp = client.clients.switch_to_client_portal("client123", "")
        self.assertEqual(resp.url, f"{server.url}/client/key_login/abc123xyz")

    def test_switch_to_client_portal_with_contact(self):
        server = self._server_with_contacts(
            [
                {
                    "id": "contact1",
                    "is_primary": True,
                    "contact_key": "primary_key_123",
                },
                {
                    "id": "contact456",
                    "is_primary": False,
                    "contact_key": "def456abc",
                },
            ]
        )
        client = Client("test-token", base_url=server.url)

        resp = client.clients.switch_to_client_portal("client123", "contact456")
        self.assertEqual(resp.url, f"{server.url}/client/key_login/def456abc")

    def test_switch_to_client_portal_no_contacts(self):
        server = self._server_with_contacts([])
        client = Client("test-token", base_url=server.url)

        with self.assertRaises(ValueError) as ctx:
            client.clients.switch_to_client_portal("client123", "")
        self.assertEqual(str(ctx.exception), "client has no contacts")

    def test_switch_to_client_portal_contact_not_found(self):
        server = self._server_with_contacts([{"id": "contact1", "contact_key": "abc"}])
        client = Client("test-token", base_url=server.url)

        with self.assertRaises(ValueError) as ctx:
            client.clients.switch_to_client_portal("client123", "nonexistent")
        self.assertEqual(str(ctx.exception), "contact with ID nonexistent not found")

    def test_switch_to_client_portal_no_contact_key(self):
        server = self._server_with_contacts([{"id": "contact1", "is_primary": True}])
        client = Client("test-token", base_url=server.url)

        with self.assertRaises(ValueError) as ctx:
            client.clients.switch_to_client_portal("client123", "")
        self.assertEqual(
            str(ctx.exception),
            "contact has no contact_key - portal access may be disabled",
        )

    def test_get_client_portal_url(self):
        server = self._server_with_contacts([{"id": "contact1", "is_primary": True, "contact_key": "primary123"}])
        client = Client("test-token", base_url=server.url)

        resp = client.clients.get_client_portal_url("client123")
        self.assertEqual(resp.url, f"{server.url}/client/key_login/primary123")

    def test_switch_to_client_portal_uses_first_contact_without_primary(self):
        server = self._server_with_contacts(
            [
                {"id": "contact1", "is_primary": False, "contact_key": "first_key"},
                {"id": "contact2", "is_primary": False, "contact_key": "second_key"},
            ]
        )
        client = Client("test-token", base_url=server.url)

        resp = client.clients.switch_to_client_portal("client123", "")
        self.assertEqual(resp.url, f"{server.url}/client/key_login/first_key")


class TestClientListOptions(unittest.TestCase):
    def test_to_query(self):
        opts = ClientListOptions(
            per_page=10,
            page=2,
            filter="test",
            balance="gt:1000",
            status="active",
            created_at="2024-01-01",
            updated_at="2024-01-15",
            is_deleted=True,
            sort="name|desc",
            include="contacts",
        )

        q = opts.to_query()

        self.assertEqual(q["per_page"], ["10"])
        self.assertEqual(q["page"], ["2"])
        self.assertEqual(q["balance"], ["gt:1000"])
        self.assertEqual(q["is_deleted"], ["true"])
        self.assertEqual(q["sort"], ["name|desc"])

    def test_to_query_omits_unset_fields(self):
        self.assertEqual(ClientListOptions().to_query(), {})


if __name__ == "__main__":
    unittest.main()
