"""Tests for the Client, ported from client_test.go."""

import json
import unittest
from typing import Optional

from invoice_ninja import (
    APIError,
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    Client,
    NetworkError,
    is_api_error,
)
from invoice_ninja.client import HTTPResponse, UrllibTransport
from invoice_ninja.errors import Headers

from .support import TestServer


class FakeTransport:
    """A custom transport double mirroring Go's custom *http.Client."""

    def __init__(self, default_timeout: Optional[float] = None) -> None:
        self.default_timeout = default_timeout
        self.received_timeout: Optional[float] = None

    def request(self, method, url, headers, body, timeout):
        self.received_timeout = timeout
        return HTTPResponse(200, Headers(), b"{}")


class TestNewClient(unittest.TestCase):
    def test_new_client(self):
        client = Client("test-token")
        self.assertEqual(client.api_token, "test-token")
        self.assertEqual(client.base_url, DEFAULT_BASE_URL)

    def test_new_client_with_options(self):
        custom_http = FakeTransport()
        custom_url = "https://custom.example.com"

        client = Client("test-token", http_client=custom_http, base_url=custom_url)

        self.assertIs(client._http, custom_http)
        self.assertEqual(client.base_url, custom_url)

    def test_set_base_url(self):
        client = Client("test-token")
        client.set_base_url("https://custom.example.com/")
        # Should trim the trailing slash.
        self.assertEqual(client.base_url, "https://custom.example.com")

    def test_with_timeout(self):
        client = Client("test-token", timeout=5)
        self.assertEqual(client._timeout, 5)

    def test_with_timeout_before_http_client(self):
        custom_http = FakeTransport()
        client = Client("test-token", timeout=5, http_client=custom_http)
        self.assertEqual(client._timeout, 5)
        # The custom client is not modified.
        self.assertIsNone(custom_http.default_timeout)

    def test_with_timeout_does_not_modify_custom_http_client(self):
        custom_http = FakeTransport(default_timeout=60)
        client = Client("test-token", http_client=custom_http, timeout=5)
        self.assertEqual(client._timeout, 5)
        self.assertEqual(custom_http.default_timeout, 60)

    def test_with_http_client_none(self):
        client = Client("test-token", http_client=None)
        self.assertIsInstance(client._http, UrllibTransport)
        self.assertEqual(client._timeout, DEFAULT_TIMEOUT)


class TestClientRequest(unittest.TestCase):
    def test_client_request(self):
        def callback(request):
            # Verify headers.
            self.assertEqual(request.header("X-API-TOKEN"), "test-token")
            self.assertEqual(request.header("X-Requested-With"), "XMLHttpRequest")
            self.assertEqual(request.header("Content-Type"), "application/json")
            self.assertEqual(request.header("User-Agent").split("/")[0], "py-invoice-ninja")
            return 200, {"Content-Type": "application/json"}, b'{"status": "ok"}'

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        result = client.request("GET", "/test")

        self.assertEqual(result["status"], "ok")

    def test_client_request_error(self):
        def callback(request):
            return 401, {}, json.dumps({"message": "Invalid API token"}).encode()

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("invalid-token", base_url=server.url)
        with self.assertRaises(Exception) as ctx:
            client.request("GET", "/test")

        api_err = is_api_error(ctx.exception)
        self.assertIsNotNone(api_err)
        self.assertTrue(api_err.is_unauthorized())

    def test_client_request_error_headers(self):
        def callback(request):
            return 429, {"Retry-After": "30"}, b""

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        with self.assertRaises(APIError) as ctx:
            client.request("GET", "/test")

        self.assertEqual(ctx.exception.headers.get("Retry-After"), "30")

    def test_client_request_network_error(self):
        # Grab a port, then close the server so connections fail.
        server = TestServer(lambda request: (200, {}, b"{}"))
        server_url = server.url
        server.close()

        client = Client("test-token", base_url=server_url)
        with self.assertRaises(Exception) as ctx:
            client.request("GET", "/test")

        self.assertIsInstance(ctx.exception, NetworkError)
        self.assertTrue(str(ctx.exception).startswith("request failed: "))
        self.assertIsNone(is_api_error(ctx.exception))

    def test_client_request_with_body(self):
        def callback(request):
            body = json.loads(request.body.decode("utf-8"))
            self.assertEqual(body["name"], "Test Client")
            return (
                200,
                {"Content-Type": "application/json"},
                json.dumps({"data": {"id": "abc123", "name": "Test Client"}}).encode(),
            )

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        result = client.request("POST", "/test", {"name": "Test Client"})
        self.assertEqual(result["data"]["id"], "abc123")

    def test_client_request_query_sorted_and_encoded(self):
        seen = {}

        def callback(request):
            seen["target"] = request.target
            return 200, {}, b"{}"

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        client.request_with_query("GET", "/test", {"per_page": "5", "page": "1"})
        self.assertEqual(seen["target"], "/test?page=1&per_page=5")


if __name__ == "__main__":
    unittest.main()
