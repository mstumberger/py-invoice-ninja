"""Tests for webhook handling, ported from webhooks_test.go."""

import hashlib
import hmac
import io
import unittest

from invoice_ninja import (
    MAX_WEBHOOK_BODY_BYTES,
    WEBHOOK_EVENT_HEADER,
    WEBHOOK_SECRET_HEADER,
    WebhookEvent,
    WebhookHandler,
)

# A payment webhook body as Invoice Ninja sends it: only the entity.
INVOICE_NINJA_PAYMENT = '{"id":"pay123","amount":100.5,"client_id":"client123","number":"0001"}'


def call_wsgi(app, method="POST", path="/webhook", body=b"", headers=None):
    """Invoke a WSGI app like Go's httptest.NewRequest + NewRecorder."""
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path.split("?")[0],
        "QUERY_STRING": path.split("?")[1] if "?" in path else "",
        "CONTENT_LENGTH": str(len(body)),
        "CONTENT_TYPE": "application/json",
        "wsgi.input": io.BytesIO(body),
        "wsgi.errors": io.StringIO(),
    }
    for name, value in (headers or {}).items():
        environ["HTTP_" + name.upper().replace("-", "_")] = value

    captured = {}

    def start_response(status, response_headers):
        captured["status"] = int(status.split()[0])
        captured["headers"] = dict(response_headers)

    chunks = app(environ, start_response)
    return captured["status"], captured["headers"], b"".join(chunks)


class TestWebhookHandler(unittest.TestCase):
    def test_webhook_handler(self):
        handler = WebhookHandler("")

        received = []
        handler.on_payment_created(lambda event: received.append(event))

        body = b'{"event_type": "payment.created", "data": {"id": "pay123", "amount": 100.0}}'
        status, _, _ = call_wsgi(handler, body=body, headers={"Content-Type": "application/json"})

        self.assertEqual(status, 200)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].event_type, "payment.created")

    def test_invoice_ninja_payload(self):
        handler = WebhookHandler("")

        received = []

        def on_payment(event):
            received.append(event.parse_payment())

        handler.on_payment_created(on_payment)

        status, _, _ = call_wsgi(
            handler,
            body=INVOICE_NINJA_PAYMENT.encode(),
            headers={"Content-Type": "application/json", WEBHOOK_EVENT_HEADER: "payment.created"},
        )

        self.assertEqual(status, 200)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].id, "pay123")
        self.assertEqual(received[0].amount, 100.5)

    def test_event_from_query_parameter(self):
        handler = WebhookHandler("")

        received = []

        def on_invoice(event):
            received.append(event.parse_invoice())

        handler.on_invoice_updated(on_invoice)

        body = b'{"id":"inv123","number":"INV001","amount":500,"entity_type":"invoice"}'
        status, _, _ = call_wsgi(handler, path="/webhook?event=invoice.updated", body=body)

        self.assertEqual(status, 200)
        self.assertEqual(received[0].number, "INV001")

    def test_accepts_put(self):
        handler = WebhookHandler("")
        called = []
        handler.on_payment_created(lambda event: called.append(1))

        status, _, _ = call_wsgi(
            handler,
            method="PUT",
            path="/webhook?event=payment.created",
            body=INVOICE_NINJA_PAYMENT.encode(),
        )
        self.assertEqual(status, 200)
        self.assertEqual(called, [1])

    def test_missing_event_name(self):
        handler = WebhookHandler("")
        called = []
        handler.on_payment_created(lambda event: called.append(1))

        status, _, _ = call_wsgi(handler, body=INVOICE_NINJA_PAYMENT.encode())
        self.assertEqual(status, 400)
        self.assertEqual(called, [])

    def test_invalid_json(self):
        handler = WebhookHandler("")
        status, _, _ = call_wsgi(
            handler, path="/webhook?event=payment.created", body=b"not json"
        )
        self.assertEqual(status, 400)

    def test_secret_header(self):
        cases = [
            ("valid secret", "test-secret", 200, True),
            ("wrong secret", "wrong-secret", 401, False),
            ("missing secret", "", 401, False),
        ]
        for name, secret, expected_status, expect_called in cases:
            with self.subTest(name):
                handler = WebhookHandler("test-secret")
                called = []
                handler.on_payment_created(lambda event: called.append(1))

                headers = {WEBHOOK_EVENT_HEADER: "payment.created"}
                if secret:
                    headers[WEBHOOK_SECRET_HEADER] = secret

                status, _, _ = call_wsgi(handler, body=INVOICE_NINJA_PAYMENT.encode(), headers=headers)
                self.assertEqual(status, expected_status)
                self.assertEqual(bool(called), expect_called)

    def test_invalid_signature(self):
        handler = WebhookHandler("test-secret")
        handler.on_invoice_created(lambda event: None)

        payload = b'{"event_type":"invoice.created","data":{"id":"inv123"}}'
        status, _, _ = call_wsgi(
            handler,
            body=payload,
            headers={"Content-Type": "application/json", "X-Ninja-Signature": "invalid-signature"},
        )
        self.assertEqual(status, 401)

    def test_valid_signature(self):
        secret = "test-secret"
        payload = b'{"event_type":"invoice.created","data":{"id":"inv123"}}'

        signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        for header_value in (signature, "sha256=" + signature):
            with self.subTest(header=header_value):
                handler = WebhookHandler(secret)
                received = []
                handler.on_invoice_created(lambda event: received.append(event))

                status, _, _ = call_wsgi(
                    handler,
                    body=payload,
                    headers={"Content-Type": "application/json", "X-Ninja-Signature": header_value},
                )
                self.assertEqual(status, 200)
                self.assertEqual(len(received), 1)
                self.assertEqual(received[0].parse_invoice().id, "inv123")

    def test_valid_signature_legacy_header(self):
        secret = "test-secret"
        payload = b'{"event_type":"invoice.created","data":{"id":"inv123"}}'
        signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        handler = WebhookHandler(secret)
        received = []
        handler.on_invoice_created(lambda event: received.append(event))

        status, _, _ = call_wsgi(
            handler,
            body=payload,
            headers={"X-Invoice-Ninja-Signature": signature},
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(received), 1)

    def test_method_not_allowed(self):
        handler = WebhookHandler("")
        status, headers, _ = call_wsgi(handler, method="GET")
        self.assertEqual(status, 405)
        self.assertEqual(headers.get("Allow"), "POST, PUT")

    def test_body_too_large(self):
        handler = WebhookHandler("")
        body = b"a" * (MAX_WEBHOOK_BODY_BYTES + 1)
        status, _, _ = call_wsgi(handler, path="/webhook?event=payment.created", body=body)
        self.assertEqual(status, 413)

    def test_handler_error_is_not_exposed(self):
        handler = WebhookHandler("")

        def failing_handler(event):
            raise RuntimeError("database password is hunter2")

        handler.on_payment_created(failing_handler)

        status, _, body = call_wsgi(
            handler, path="/webhook?event=payment.created", body=INVOICE_NINJA_PAYMENT.encode()
        )
        self.assertEqual(status, 500)
        self.assertNotIn(b"hunter2", body)

    def test_unregistered_event(self):
        handler = WebhookHandler("")
        body = b'{"event_type":"unknown.event","data":{}}'
        status, _, _ = call_wsgi(handler, body=body)
        self.assertEqual(status, 200)

    def test_registration_helpers(self):
        handler = WebhookHandler("")
        noop = lambda event: None  # noqa: E731

        handler.on_invoice_created(noop)
        handler.on_invoice_updated(noop)
        handler.on_invoice_deleted(noop)
        handler.on_payment_created(noop)
        handler.on_payment_updated(noop)
        handler.on_payment_deleted(noop)
        handler.on_client_created(noop)
        handler.on_client_updated(noop)
        handler.on_credit_created(noop)
        handler.on_quote_created(noop)

        events = [
            "invoice.created",
            "invoice.updated",
            "invoice.deleted",
            "payment.created",
            "payment.updated",
            "payment.deleted",
            "client.created",
            "client.updated",
            "credit.created",
            "quote.created",
        ]
        for event in events:
            self.assertIn(event, handler.handlers)

    def test_process_directly(self):
        """The framework-agnostic process() entry point."""
        handler = WebhookHandler("")
        received = []
        handler.on_payment_created(lambda event: received.append(event))

        status, body, extra_headers = handler.process(
            "POST",
            {WEBHOOK_EVENT_HEADER: "payment.created"},
            "",
            INVOICE_NINJA_PAYMENT.encode(),
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].parse_payment().id, "pay123")


class TestWebhookEventParsers(unittest.TestCase):
    def test_parse_invoice(self):
        event = WebhookEvent(
            event_type="invoice.created",
            data=b'{"id":"inv123","number":"INV001","amount":500.00}',
        )
        invoice = event.parse_invoice()
        self.assertEqual(invoice.id, "inv123")
        self.assertEqual(invoice.amount, 500.0)

    def test_parse_payment(self):
        event = WebhookEvent(
            event_type="payment.created",
            data=b'{"id":"pay123","amount":100.00,"client_id":"client123"}',
        )
        payment = event.parse_payment()
        self.assertEqual(payment.id, "pay123")

    def test_parse_client(self):
        event = WebhookEvent(
            event_type="client.created",
            data=b'{"id":"client123","name":"Acme Corp"}',
        )
        client = event.parse_client()
        self.assertEqual(client.id, "client123")
        self.assertEqual(client.name, "Acme Corp")

    def test_parse_credit(self):
        event = WebhookEvent(
            event_type="credit.created",
            data=b'{"id":"credit123","number":"CR001","amount":50.00}',
        )
        credit = event.parse_credit()
        self.assertEqual(credit.id, "credit123")

    def test_parse_invalid_data_raises(self):
        event = WebhookEvent(event_type="invoice.created", data=b"not json")
        with self.assertRaises(ValueError) as ctx:
            event.parse_invoice()
        self.assertTrue(str(ctx.exception).startswith("failed to parse invoice data:"))


if __name__ == "__main__":
    unittest.main()
