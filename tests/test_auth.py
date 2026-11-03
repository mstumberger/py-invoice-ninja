"""Tests for email/password login, mirroring the real usage in the wild:
token in the X-Auth-Token header, with body fallbacks for cloud/self-hosted
builds that return the CompanyToken in the response body."""

import json
import unittest

from invoice_ninja import (
    APIError,
    Client,
    InvoiceNinjaError,
    NetworkError,
    login,
)

from .support import TestServer


def _json(payload):
    return json.dumps(payload).encode("utf-8")


class TestLogin(unittest.TestCase):
    def test_login_posts_credentials(self):
        captured = {}

        def callback(request):
            captured["method"] = request.method
            captured["path"] = request.path
            captured["body"] = json.loads(request.body.decode("utf-8"))
            captured["x_requested_with"] = request.header("X-Requested-With")
            captured["content_type"] = request.header("Content-Type")
            return 200, {"X-Auth-Token": "header-token"}, b"[]"

        server = TestServer(callback)
        self.addCleanup(server.close)

        token = login("user@example.com", "pw", server.url)

        self.assertEqual(token, "header-token")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["path"], "/api/v1/login")
        self.assertEqual(captured["body"], {"email": "user@example.com", "password": "pw"})
        self.assertEqual(captured["x_requested_with"], "XMLHttpRequest")
        self.assertEqual(captured["content_type"], "application/json")

    def test_token_from_header_wins_over_body(self):
        server = TestServer(
            lambda request: (200, {"X-Auth-Token": "from-header"}, _json({"token": "from-body"}))
        )
        self.addCleanup(server.close)

        self.assertEqual(login("user@example.com", "pw", server.url), "from-header")

    def test_falls_back_to_body_token(self):
        server = TestServer(lambda request: (200, {}, _json({"token": "from-body"})))
        self.addCleanup(server.close)

        self.assertEqual(login("user@example.com", "pw", server.url), "from-body")

    def test_falls_back_to_data_entry_token_string(self):
        body = {"data": [{"token": "company-token"}, {"token": ""}]}
        server = TestServer(lambda request: (200, {}, _json(body)))
        self.addCleanup(server.close)

        self.assertEqual(login("user@example.com", "pw", server.url), "company-token")

    def test_falls_back_to_data_entry_token_object(self):
        # Some builds return the CompanyToken as an object with a token field.
        body = {"data": [{"token": {"token": "nested-token", "name": "Default"}}]}
        server = TestServer(lambda request: (200, {}, _json(body)))
        self.addCleanup(server.close)

        self.assertEqual(login("user@example.com", "pw", server.url), "nested-token")

    def test_api_secret_header_sent_when_given(self):
        captured = {}

        def callback(request):
            captured["secret"] = request.header("X-API-SECRET")
            return 200, {"X-Auth-Token": "t"}, b"[]"

        server = TestServer(callback)
        self.addCleanup(server.close)

        login("user@example.com", "pw", server.url, api_secret="sekrit")
        self.assertEqual(captured["secret"], "sekrit")

    def test_wrong_credentials_raises_api_error(self):
        server = TestServer(
            lambda request: (401, {}, _json({"message": "These credentials do not match our records"}))
        )
        self.addCleanup(server.close)

        with self.assertRaises(APIError) as ctx:
            login("user@example.com", "wrong", server.url)
        self.assertTrue(ctx.exception.is_unauthorized())

    def test_no_token_raises(self):
        server = TestServer(lambda request: (200, {}, _json([{"id": "cu1"}])))
        self.addCleanup(server.close)

        with self.assertRaises(InvoiceNinjaError) as ctx:
            login("user@example.com", "pw", server.url)
        self.assertEqual(str(ctx.exception), "Invoice Ninja login succeeded but returned no token")

    def test_missing_credentials_raises_value_error(self):
        with self.assertRaises(ValueError):
            login("", "pw")
        with self.assertRaises(ValueError):
            login("user@example.com", "")

    def test_login_base_url_trailing_slash(self):
        server = TestServer(lambda request: (200, {"X-Auth-Token": "t"}, b"[]"))
        self.addCleanup(server.close)

        token = login("user@example.com", "pw", server.url + "/")
        self.assertEqual(token, "t")

    def test_login_network_error(self):
        server = TestServer(lambda request: (200, {}, b""))
        url = server.url
        server.close()

        with self.assertRaises(NetworkError):
            login("user@example.com", "pw", url)


class TestClientFromLogin(unittest.TestCase):
    def test_from_login_builds_authenticated_client(self):
        def callback(request):
            if request.path == "/api/v1/login":
                return 200, {"X-Auth-Token": "fresh-token"}, b"[]"
            self.assertEqual(request.header("X-API-TOKEN"), "fresh-token")
            return 200, {}, _json({"data": []})

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client.from_login("user@example.com", "pw", base_url=server.url)
        self.assertEqual(client.api_token, "fresh-token")
        # The client works against the API right away.
        client.payments.list()


if __name__ == "__main__":
    unittest.main()
