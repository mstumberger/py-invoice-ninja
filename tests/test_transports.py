"""Tests for the optional requests-based transport."""

import json
import sys
import unittest
from unittest import mock

from invoice_ninja import Client, APIError, NetworkError

from .support import TestServer

try:
    import requests  # noqa: F401

    HAVE_REQUESTS = True
except ImportError:  # pragma: no cover - depends on environment
    HAVE_REQUESTS = False


def _json(payload):
    return json.dumps(payload).encode("utf-8")


@unittest.skipUnless(HAVE_REQUESTS, "requests is not installed")
class TestRequestsTransport(unittest.TestCase):
    def test_client_works_through_requests_transport(self):
        def callback(request):
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.path, "/api/v1/payments")
            self.assertEqual(request.header("X-API-TOKEN"), "test-token")
            self.assertEqual(request.header("User-Agent").split("/")[0], "py-invoice-ninja")
            return (
                200,
                {"Content-Type": "application/json"},
                _json({"data": [{"id": "p1", "amount": 12.5}], "meta": {"pagination": {"total": 1}}}),
            )

        server = TestServer(callback)
        self.addCleanup(server.close)

        from invoice_ninja.transports import RequestsTransport

        client = Client("test-token", base_url=server.url, http_client=RequestsTransport())
        resp = client.payments.list()

        self.assertEqual(resp.data[0].id, "p1")
        self.assertEqual(resp.data[0].amount, 12.5)

    def test_post_body_reaches_server(self):
        def callback(request):
            body = json.loads(request.body.decode("utf-8"))
            self.assertEqual(body["client_id"], "c1")
            self.assertEqual(request.header("Content-Type"), "application/json")
            return 200, {}, _json({"data": {"id": "new1"}})

        server = TestServer(callback)
        self.addCleanup(server.close)

        from invoice_ninja.transports import RequestsTransport
        from invoice_ninja import PaymentRequest

        client = Client("test-token", base_url=server.url, http_client=RequestsTransport())
        payment = client.payments.create(PaymentRequest(client_id="c1", amount=5))
        self.assertEqual(payment.id, "new1")

    def test_api_error_through_requests_transport(self):
        server = TestServer(lambda request: (404, {}, _json({"message": "nope"})))
        self.addCleanup(server.close)

        from invoice_ninja.transports import RequestsTransport

        client = Client("test-token", base_url=server.url, http_client=RequestsTransport())
        with self.assertRaises(APIError) as ctx:
            client.payments.get("missing")
        self.assertTrue(ctx.exception.is_not_found())

    def test_network_error_wrapped(self):
        server = TestServer(lambda request: (200, {}, b"{}"))
        url = server.url
        server.close()

        from invoice_ninja.transports import RequestsTransport

        client = Client("test-token", base_url=url, http_client=RequestsTransport())
        with self.assertRaises(NetworkError):
            client.payments.list()

    def test_custom_session_is_used(self):
        import requests as requests_lib

        from invoice_ninja.transports import RequestsTransport

        session = requests_lib.Session()
        transport = RequestsTransport(session=session)
        self.assertIs(transport.session, session)

    def test_missing_requests_gives_helpful_error(self):
        with mock.patch.dict(sys.modules, {"requests": None}):
            # Re-import fresh so the lazy import inside __init__ runs.
            import importlib

            import invoice_ninja.transports as transports_module

            importlib.reload(transports_module)
            with self.assertRaises(ImportError) as ctx:
                transports_module.RequestsTransport()
            self.assertIn("pip install requests", str(ctx.exception))
        importlib.reload(transports_module)


if __name__ == "__main__":
    unittest.main()
