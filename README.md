# Python Invoice Ninja SDK

A professional, dependency-free Python SDK for the [Invoice Ninja](https://invoiceninja.com) API. This is a full Python port of the Go SDK [go-invoice-ninja](https://github.com/AshkanYarmoradi/go-invoice-ninja), providing a clean interface for interacting with Invoice Ninja's comprehensive invoicing and payment platform.

## Features

- Secure authentication - token-based API authentication (`X-API-TOKEN`)
- Payment management - full CRUD operations with refund support
- Invoice operations - create, send, and manage invoices
- Client management - client CRUD with merge capabilities
- Credits and payment terms - complete credit and terms management
- File operations - download PDFs and upload documents (multipart)
- Webhook handling - WSGI handler with secret and HMAC signature verification
- Rate limiting - client-side limiting with a sliding window
- Retry logic - exponential backoff for transient failures, `Retry-After` aware
- Self-hosted support - works with cloud and self-hosted instances
- Fully tested - 160+ tests, stdlib only (no third-party dependencies)

## Installation

Copy the `invoice_ninja` package into your project, or install from this directory:

```bash
pip install .
```

## Quick Start

```python
from invoice_ninja import Client, PaymentListOptions

# Create a new client
client = Client("your-api-token")

# For self-hosted instances:
# client = Client("your-api-token", base_url="https://your-instance.com")

# List payments
payments = client.payments.list(PaymentListOptions(per_page=10, page=1))
for payment in payments.data:
    print(f"Payment {payment.number}: ${payment.amount:.2f}")
```

## Authentication

All API requests require an API token. You can obtain your token from:
**Settings > Account Management > Integrations > API tokens**

```python
client = Client("your-api-token")
```

Every request sends `X-API-TOKEN` and `X-Requested-With: XMLHttpRequest` headers, matching the Invoice Ninja API requirements.

### Logging in with email and password

You can also obtain a token programmatically with your account credentials ([docs](https://invoiceninja.github.io/docs/developer-guide/api/authentication)): `POST /api/v1/login` returns the API token in the `X-Auth-Token` response header (cloud builds may return it in the response body instead; both are handled):

```python
from invoice_ninja import Client, login

# Self-hosted: login(email, password, "https://your-instance.com")
# Server sets API_SECRET? login(email, password, api_secret="...")
token = login("you@example.com", "your-password")

client = Client(token)

# Or in one step:
client = Client.from_login("you@example.com", "your-password")
```

The login endpoint is rate-limited to a handful of calls per minute, so cache the returned token (e.g. in a file with `0600` permissions) and reuse it instead of logging in for every run. See [examples/login.py](examples/login.py) for a complete example.

## Configuration Options

```python
# Custom transport (any object with a request() method, see UrllibTransport)
client = Client("token", http_client=my_transport)

# Custom base URL (for self-hosted)
client = Client("token", base_url="https://your-instance.com")

# Custom timeout (seconds)
client = Client("token", timeout=60)

# Rate limiting and retries
from invoice_ninja import RateLimiter, default_retry_config

client = Client(
    "token",
    rate_limiter=RateLimiter(10),          # 10 requests per second
    retry_config=default_retry_config(),
)
```

## Payments

```python
from invoice_ninja import PaymentListOptions, PaymentRequest, PaymentInvoice, RefundRequest

# List payments
payments = client.payments.list(PaymentListOptions(
    per_page=20,
    page=1,
    client_id="client-hash-id",
    status="active",
    sort="amount|desc",
))

# Get / create / update / delete
payment = client.payments.get("payment-hash-id")
payment = client.payments.create(PaymentRequest(
    client_id="client-hash-id",
    amount=100.00,
    date="2024-01-15",
    invoices=[PaymentInvoice(invoice_id="invoice-hash-id", amount=100.00)],
))
payment = client.payments.update("payment-hash-id", PaymentRequest(private_notes="Updated notes"))
client.payments.delete("payment-hash-id")

# Refund
payment = client.payments.refund(RefundRequest(
    id="payment-hash-id",
    amount=50.00,
    gateway_refund=True,
))

# Bulk actions
payments = client.payments.bulk("archive", ["id1", "id2"])

# Single item convenience methods
payment = client.payments.archive("payment-hash-id")
payment = client.payments.restore("payment-hash-id")
```

## Invoices

```python
from invoice_ninja import Invoice, InvoiceListOptions, LineItem

invoices = client.invoices.list(InvoiceListOptions(per_page=20, client_id="client-hash-id"))
invoice = client.invoices.get("invoice-hash-id")
invoice = client.invoices.create(Invoice(
    client_id="client-hash-id",
    line_items=[LineItem(product_key="Product A", quantity=2, cost=50.00)],
))

# Invoice actions
invoice = client.invoices.mark_paid("invoice-hash-id")
invoice = client.invoices.mark_sent("invoice-hash-id")
invoice = client.invoices.email("invoice-hash-id")

# Download the PDF by invitation key
pdf_bytes = client.invoices.download("invitation-key")
```

## Clients

```python
from invoice_ninja import INClient, ClientContact, ClientListOptions

clients = client.clients.list(ClientListOptions(
    per_page=20,
    balance="gt:1000",            # Balance greater than 1000
    include="contacts,documents",
))

new_client = client.clients.create(INClient(
    name="Acme Corporation",
    contacts=[ClientContact(
        first_name="John", last_name="Doe",
        email="john@acme.com", is_primary=True,
    )],
))

# Merge two clients
merged = client.clients.merge("primary-id", "mergeable-id")

# Client portal magic link
portal = client.clients.get_client_portal_url("client-id")
print(portal.url)
```

## Payment Terms

```python
from invoice_ninja import PaymentTerm

terms = client.payment_terms.list()
term = client.payment_terms.create(PaymentTerm(name="Net 45", num_days=45))
term = client.payment_terms.get("term-id")
term = client.payment_terms.update("term-id", PaymentTerm(name="Net 60"))
client.payment_terms.delete("term-id")
```

## Credits

```python
from invoice_ninja import Credit, CreditListOptions, LineItem

credits = client.credits.list(CreditListOptions(client_id="client-hash-id", per_page=20))
credit = client.credits.create(Credit(
    client_id="client-hash-id",
    line_items=[LineItem(product_key="Credit", quantity=1, cost=100.00)],
))

credit = client.credits.mark_sent("credit-id")
credit = client.credits.email("credit-id")
```

## File Downloads

```python
# Download invoice PDF
pdf = client.downloads.download_invoice_pdf("invitation-key")

# Download delivery note
pdf = client.downloads.download_invoice_delivery_note("invoice-id")

# Download credit / quote PDFs
pdf = client.downloads.download_credit_pdf("invitation-key")
pdf = client.downloads.download_quote_pdf("invitation-key")

# Save to file
with open("invoice.pdf", "wb") as handle:
    handle.write(pdf)
```

## File Uploads

```python
# Upload document to an invoice
client.uploads.upload_invoice_document("invoice-id", "/path/to/file.pdf")

# Upload to other entities
client.uploads.upload_payment_document("payment-id", "/path/to/file.pdf")
client.uploads.upload_client_document("client-id", "/path/to/file.pdf")
client.uploads.upload_credit_document("credit-id", "/path/to/file.pdf")

# Upload from a binary file object
import io
client.uploads.upload_document_from_reader(
    "invoices", "invoice-id", "document.pdf", io.BytesIO(pdf_content)
)
```

## Webhooks

Handle incoming webhooks from Invoice Ninja. `WebhookHandler` is a WSGI application:

```python
from invoice_ninja import WebhookHandler

# Create a webhook handler that requires the X-Webhook-Secret header
handler = WebhookHandler("your-webhook-secret")

# Register event handlers
def on_payment_created(event):
    payment = event.parse_payment()
    print(f"New payment: {payment.number} (${payment.amount:.2f})")

def on_invoice_created(event):
    invoice = event.parse_invoice()
    print(f"New invoice: {invoice.number}")

handler.on_payment_created(on_payment_created)
handler.on_invoice_created(on_invoice_created)

# Use with any WSGI server
from wsgiref.simple_server import make_server
with make_server("", 8080, handler) as httpd:
    httpd.serve_forever()
```

For non-WSGI frameworks (Flask, FastAPI, Django), call the framework-agnostic core directly:

```python
status, body, extra_headers = handler.process(
    method, headers, query_string, raw_body,
)
```

Invoice Ninja sends only the entity (for example the payment) in a webhook, without the event name or a signature. For each webhook you create in Invoice Ninja (Settings > Account Management > Integrations > API Webhooks):
- Put the event name in the target URL, e.g. `https://your-server.com/webhook?event=payment.created` (or add an `X-Webhook-Event` header)
- Add an `X-Webhook-Secret` header with your secret

Supported webhook events:
- `on_invoice_created`, `on_invoice_updated`, `on_invoice_deleted` (`invoice.created`, `invoice.updated`, `invoice.deleted`)
- `on_payment_created`, `on_payment_updated`, `on_payment_deleted` (`payment.created`, `payment.updated`, `payment.deleted`)
- `on_client_created`, `on_client_updated` (`client.created`, `client.updated`)
- `on_credit_created`, `on_quote_created` (`credit.created`, `quote.created`)
- `on("event.name", handler)` for any other event

## Rate Limiting and Retry

Rate limiting and automatic retries are off by default. Turn them on with client options:

```python
from invoice_ninja import Client, RateLimiter, default_retry_config

client = Client(
    "your-api-token",
    rate_limiter=RateLimiter(10),  # 10 requests per second
    retry_config=default_retry_config(),
)
```

Or use the rate-limited client, which starts with 10 requests per second and `default_retry_config()`:

```python
from invoice_ninja import RateLimitedClient

# Create a rate-limited client
client = RateLimitedClient("your-api-token", base_url="https://your-instance.com")

# Change the rate limit (requests per second)
client.set_rate_limit(5)

# Change the retry behavior
from invoice_ninja import RetryConfig

client.set_retry_config(RetryConfig(
    max_retries=3,
    initial_backoff=1.0,      # seconds
    max_backoff=30.0,
    backoff_multiplier=2.0,
    retry_on_status_codes=(429, 500, 502, 503, 504),
    jitter=True,
))

# Service methods and generic requests use the rate limiter and retries
payments = client.payments.list()
```

How retries work:
- Network errors and the status codes in `retry_on_status_codes` are retried with exponential backoff, up to `max_retries` times.
- For `429` responses the `Retry-After` header is honored. If it asks for a longer wait than `max_backoff`, the error is raised instead.
- `POST` and `PATCH` requests (such as creating a payment or emailing an invoice) are only retried after a `429`, because the server may already have processed them. Set `retry_non_idempotent=True` to retry them in every case.

## Generic Requests

For API endpoints not covered by specialized methods, use the generic request:

```python
# GET request
activities = client.request("GET", "/api/v1/activities")

# POST request with body
result = client.request("POST", "/api/v1/products", {"name": "New Product", "cost": 99.99})

# With query parameters
result = client.request_with_query("GET", "/api/v1/products", {"per_page": "50"})
```

## Error Handling

The SDK provides typed errors with helper methods:

```python
from invoice_ninja import APIError, is_api_error

try:
    payment = client.payments.get("invalid-id")
except APIError as api_err:
    if api_err.is_not_found():
        print("Payment not found")
    elif api_err.is_unauthorized():
        print("Invalid API token")
    elif api_err.is_validation_error():
        print(f"Validation errors: {api_err.errors}")
    elif api_err.is_rate_limited():
        print("Rate limit exceeded, please wait")
except Exception as err:
    print(f"Network or other error: {err}")
```

`is_api_error(err)` returns the `APIError` if *err* is one, otherwise `None`. All SDK errors derive from `InvoiceNinjaError`.

## Testing

```bash
# Run all tests (stdlib unittest, no dependencies)
make test
# or
python3 -m unittest

# With coverage
make coverage

# Run the linter
make lint
```

## Integration Tests

Run integration tests against a live Invoice Ninja server:

```bash
# Run against demo server
INVOICE_NINJA_RUN_INTEGRATION=1 python3 -m unittest tests.test_integration

# Run against custom server
INVOICE_NINJA_BASE_URL=https://your-server.com \
INVOICE_NINJA_API_TOKEN=your-token \
INVOICE_NINJA_RUN_INTEGRATION=1 \
python3 -m unittest tests.test_integration
```

## Examples

Check out the `examples/` directory for complete working examples:

- [Basic usage](examples/basic.py) - getting started
- [Login with email/password](examples/login.py) - obtaining an API token
- [Invoice management](examples/invoices.py) - creating and managing invoices
- [Webhook handling](examples/webhooks.py) - setting up webhook handlers

## API Reference

| Status Code | Description |
|-------------|-------------|
| 200 | Success |
| 400 | Bad Request |
| 401 | Unauthorized - Invalid API token |
| 403 | Forbidden - No permission |
| 404 | Not Found |
| 422 | Validation Error |
| 429 | Rate Limited |
| 5xx | Server Error |

## Differences from the Go SDK

- Context-based cancellation (`ctx`) has no Python equivalent; use the client-level `timeout`.
- `WebhookHandler` is a WSGI callable instead of `http.Handler`; `handler.process(...)` exposes the same logic for any web framework.
- The default HTTP transport is urllib (no third-party dependencies). Pass `http_client=` with a `request(method, url, headers, body, timeout)` method to plug in requests/httpx/urllib3.
- The model class for clients is named `INClient` (like Go) to avoid clashing with the API `Client`.

## License

This SDK is released under the [MIT License](LICENSE), same as the original Go SDK.

## Credits

This project is a full Python rewrite of the Go SDK
[go-invoice-ninja](https://github.com/AshkanYarmoradi/go-invoice-ninja) by
[Ashkan Yarmoradi](https://github.com/AshkanYarmoradi). All credit for the original
design, API surface and test suite goes to the original author; this port keeps the
MIT license and the original copyright notice.
