"""Webhook handling for the Invoice Ninja SDK.

Invoice Ninja webhook requests contain only the entity that changed (for
example an invoice or a payment) as JSON. They carry neither the event name
nor a signature, so the event name and a shared secret come from the target
URL and headers configured for each webhook in Invoice Ninja.

:class:`WebhookHandler` is a WSGI application, so it works with any WSGI
server (wsgiref, gunicorn, waitress, ...) and most frameworks' WSGI mounts.
For non-WSGI frameworks, call :meth:`WebhookHandler.process` directly.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from .errors import Headers

from .models import Credit, INClient, Invoice, Payment

__all__ = [
    "WebhookEvent",
    "WebhookHandler",
    "WEBHOOK_EVENT_HEADER",
    "WEBHOOK_EVENT_QUERY_PARAM",
    "WEBHOOK_SECRET_HEADER",
    "MAX_WEBHOOK_BODY_BYTES",
    "SIGNATURE_HEADER",
    "LEGACY_SIGNATURE_HEADER",
]

#: Request header that names the event, such as "payment.created".
WEBHOOK_EVENT_HEADER = "X-Webhook-Event"

#: Query parameter that names the event when it is part of the webhook's
#: target URL, as in https://example.com/webhook?event=payment.created.
WEBHOOK_EVENT_QUERY_PARAM = "event"

#: Request header that must contain the secret passed to WebhookHandler.
WEBHOOK_SECRET_HEADER = "X-Webhook-Secret"

#: Largest request body WebhookHandler accepts (10 MB).
MAX_WEBHOOK_BODY_BYTES = 10 << 20

#: Headers that may carry a hex-encoded HMAC-SHA256 signature of the body
#: from custom senders.
SIGNATURE_HEADER = "X-Ninja-Signature"
LEGACY_SIGNATURE_HEADER = "X-Invoice-Ninja-Signature"

#: Type of a handler function registered with :meth:`WebhookHandler.on`.
WebhookEventHandler = Callable[["WebhookEvent"], None]


@dataclass
class WebhookEvent:
    """A webhook event received from Invoice Ninja."""

    #: Event name, such as "invoice.created" or "payment.created".
    event_type: str = ""
    #: The entity JSON, such as an invoice or a payment. Bytes, str or an
    #: already-parsed dict.
    data: Any = b""

    def _payload(self) -> Any:
        if isinstance(self.data, (bytes, bytearray)):
            return json.loads(bytes(self.data).decode("utf-8"))
        if isinstance(self.data, str):
            return json.loads(self.data)
        return self.data

    def parse_invoice(self) -> Invoice:
        """Parse the webhook data as an :class:`~invoice_ninja.Invoice`."""
        try:
            return Invoice.from_dict(self._payload())
        except (ValueError, TypeError) as err:
            raise ValueError(f"failed to parse invoice data: {err}") from err

    def parse_payment(self) -> Payment:
        """Parse the webhook data as a :class:`~invoice_ninja.Payment`."""
        try:
            return Payment.from_dict(self._payload())
        except (ValueError, TypeError) as err:
            raise ValueError(f"failed to parse payment data: {err}") from err

    def parse_client(self) -> INClient:
        """Parse the webhook data as an :class:`~invoice_ninja.INClient`."""
        try:
            return INClient.from_dict(self._payload())
        except (ValueError, TypeError) as err:
            raise ValueError(f"failed to parse client data: {err}") from err

    def parse_credit(self) -> Credit:
        """Parse the webhook data as a :class:`~invoice_ninja.Credit`."""
        try:
            return Credit.from_dict(self._payload())
        except (ValueError, TypeError) as err:
            raise ValueError(f"failed to parse credit data: {err}") from err


class WebhookHandler:
    """Handles incoming webhook requests from Invoice Ninja.

    If *secret* is not empty, every request must include it in the
    ``X-Webhook-Secret`` header. Invoice Ninja does not sign webhook requests,
    so add this header to each webhook in Invoice Ninja (Settings > Account
    Management > Integrations > API Webhooks). For custom senders, a
    hex-encoded HMAC-SHA256 signature of the body in the ``X-Ninja-Signature``
    header is accepted instead.
    """

    def __init__(self, secret: str = "") -> None:
        self.secret = secret
        self.handlers: Dict[str, WebhookEventHandler] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def on(self, event_type: str, handler: WebhookEventHandler) -> None:
        """Register a handler for an event name, such as "invoice.created"."""
        self.handlers[event_type] = handler

    def on_invoice_created(self, handler: WebhookEventHandler) -> None:
        """Register a handler for invoice.created events."""
        self.on("invoice.created", handler)

    def on_invoice_updated(self, handler: WebhookEventHandler) -> None:
        """Register a handler for invoice.updated events."""
        self.on("invoice.updated", handler)

    def on_invoice_deleted(self, handler: WebhookEventHandler) -> None:
        """Register a handler for invoice.deleted events."""
        self.on("invoice.deleted", handler)

    def on_payment_created(self, handler: WebhookEventHandler) -> None:
        """Register a handler for payment.created events."""
        self.on("payment.created", handler)

    def on_payment_updated(self, handler: WebhookEventHandler) -> None:
        """Register a handler for payment.updated events."""
        self.on("payment.updated", handler)

    def on_payment_deleted(self, handler: WebhookEventHandler) -> None:
        """Register a handler for payment.deleted events."""
        self.on("payment.deleted", handler)

    def on_client_created(self, handler: WebhookEventHandler) -> None:
        """Register a handler for client.created events."""
        self.on("client.created", handler)

    def on_client_updated(self, handler: WebhookEventHandler) -> None:
        """Register a handler for client.updated events."""
        self.on("client.updated", handler)

    def on_credit_created(self, handler: WebhookEventHandler) -> None:
        """Register a handler for credit.created events."""
        self.on("credit.created", handler)

    def on_quote_created(self, handler: WebhookEventHandler) -> None:
        """Register a handler for quote.created events."""
        self.on("quote.created", handler)

    # ------------------------------------------------------------------
    # Framework-agnostic processing
    # ------------------------------------------------------------------

    def process(
        self,
        method: str,
        headers: Mapping[str, str] | Headers,
        query_string: str,
        body: bytes,
    ) -> Tuple[int, str, Optional[Dict[str, str]]]:
        """Process an incoming webhook request and return the HTTP result.

        Returns ``(status_code, response_body, extra_headers)``. The event
        name is read from the ``X-Webhook-Event`` header, then from the
        ``event`` query parameter. A JSON body of the form
        ``{"event_type": "...", "data": {...}}`` is also accepted. The status
        is 200 when the event was handled or no handler is registered for it.
        """
        if method.upper() not in ("POST", "PUT"):
            return 405, "Method not allowed\n", {"Allow": "POST, PUT"}

        if not isinstance(headers, Headers):
            headers = Headers(headers)

        # Check the secret header before reading the body.
        secret_verified = False
        if self.secret:
            secret = headers.get(WEBHOOK_SECRET_HEADER)
            if secret:
                if not _secrets_equal(secret, self.secret):
                    return 401, "Invalid secret\n", None
                secret_verified = True
            elif not _request_signature(headers):
                return 401, "Missing secret\n", None

        # Verify the signature of custom senders that don't send the secret header.
        if self.secret and not secret_verified and not self._verify_signature(
            body, _request_signature(headers)
        ):
            return 401, "Invalid signature\n", None

        event, parse_error = _parse_webhook_event(headers, query_string, body)
        if parse_error:
            return 400, "Failed to parse webhook payload\n", None

        if not event.event_type:
            return (
                400,
                "Missing event name: set the "
                f"{WEBHOOK_EVENT_HEADER} header or the \"{WEBHOOK_EVENT_QUERY_PARAM}\" "
                "query parameter\n",
                None,
            )

        # Find and execute the handler.
        handler = self.handlers.get(event.event_type)
        if handler is None:
            # No handler registered for this event type, acknowledge receipt.
            return 200, "", None

        try:
            handler(event)
        except Exception:
            # Don't send internal error details back to the caller.
            return 500, "Webhook handler failed\n", None

        return 200, "", None

    # ------------------------------------------------------------------
    # WSGI interface
    # ------------------------------------------------------------------

    def __call__(self, environ, start_response):
        from http import HTTPStatus

        method = environ.get("REQUEST_METHOD", "GET")
        headers = _headers_from_environ(environ)
        query_string = environ.get("QUERY_STRING", "")

        try:
            body = _read_body(environ)
        except _BodyTooLargeError:
            status_code, body_text, extra_headers = 413, "Request body too large\n", None
        except (OSError, ValueError):
            status_code, body_text, extra_headers = 400, "Failed to read request body\n", None
        else:
            status_code, body_text, extra_headers = self.process(method, headers, query_string, body)

        status = f"{status_code} {HTTPStatus(status_code).phrase}"
        response_headers = [("Content-Type", "text/plain; charset=utf-8")]
        if extra_headers:
            response_headers.extend(extra_headers.items())
        response_headers.append(("Content-Length", str(len(body_text.encode("utf-8")))))
        response_headers.append(("X-Content-Type-Options", "nosniff"))
        start_response(status, response_headers)
        return [body_text.encode("utf-8")]

    def _verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify a hex-encoded HMAC-SHA256 signature of the payload."""
        if not signature:
            return False

        # Remove "sha256=" prefix if present.
        signature = signature.removeprefix("sha256=")

        expected = hmac.new(self.secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature.encode("utf-8"), expected.encode("utf-8"))


def _request_signature(headers: Headers) -> str:
    """Return the HMAC signature sent with the request, if any."""
    signature = headers.get(SIGNATURE_HEADER)
    if signature:
        return signature
    return headers.get(LEGACY_SIGNATURE_HEADER)


def _secrets_equal(a: str, b: str) -> bool:
    """Compare two secrets in constant time."""
    hash_a = hashlib.sha256(a.encode("utf-8")).digest()
    hash_b = hashlib.sha256(b.encode("utf-8")).digest()
    return hmac.compare_digest(hash_a, hash_b)


def _parse_webhook_event(headers: Headers, query_string: str, body: bytes) -> Tuple[WebhookEvent, bool]:
    """Build a WebhookEvent from the request parts and its body.

    Returns ``(event, parse_error)``; *parse_error* is True when the body is
    not valid JSON.
    """
    try:
        envelope = json.loads(body.decode("utf-8")) if body else {}
    except (ValueError, UnicodeDecodeError):
        return WebhookEvent(), True
    if not isinstance(envelope, dict):
        return WebhookEvent(), True

    event = WebhookEvent(
        event_type=headers.get(WEBHOOK_EVENT_HEADER),
        data=body,
    )
    if not event.event_type:
        event.event_type = _query_param(query_string, WEBHOOK_EVENT_QUERY_PARAM)

    # Envelope format used by custom senders: {"event_type": "...", "data": {...}}
    envelope_event_type = envelope.get("event_type")
    if envelope_event_type:
        if not event.event_type:
            event.event_type = envelope_event_type
        event.data = envelope.get("data")

    return event, False


def _query_param(query_string: str, name: str) -> str:
    import urllib.parse

    params = urllib.parse.parse_qs(query_string, keep_blank_values=True)
    values = params.get(name, [])
    return values[0] if values else ""


def _headers_from_environ(environ: Mapping[str, str]) -> Headers:
    headers = Headers()
    for key, value in environ.items():
        if key.startswith("HTTP_"):
            headers.set(key[5:].replace("_", "-"), value)
        elif key in ("CONTENT_TYPE", "CONTENT_LENGTH") and value:
            headers.set(key.replace("_", "-").lower(), value)
    return headers


class _BodyTooLargeError(Exception):
    pass


def _read_body(environ) -> bytes:
    """Read the request body from the WSGI input stream, enforcing
    ``MAX_WEBHOOK_BODY_BYTES`` like Go's ``http.MaxBytesReader``."""
    content_length = environ.get("CONTENT_LENGTH") or "0"
    try:
        length = int(content_length)
    except ValueError as err:
        raise ValueError("invalid Content-Length") from err

    if length > MAX_WEBHOOK_BODY_BYTES:
        raise _BodyTooLargeError()

    input_stream = environ.get("wsgi.input")
    if input_stream is None:
        return b""

    body = input_stream.read(length)
    if len(body) > MAX_WEBHOOK_BODY_BYTES:
        raise _BodyTooLargeError()
    return body
