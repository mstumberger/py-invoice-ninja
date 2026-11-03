"""py-invoice-ninja: a Python SDK for the Invoice Ninja API.

A full Python port of the Go SDK at
https://github.com/AshkanYarmoradi/go-invoice-ninja, supporting both
cloud-hosted (invoicing.co) and self-hosted Invoice Ninja instances.

Basic usage::

    from invoice_ninja import Client, PaymentListOptions

    client = Client("your-api-token")
    payments = client.payments.list(PaymentListOptions(per_page=10, page=1))
    for payment in payments.data:
        print(payment.number, payment.amount)

Authentication: all requests require an API token obtained from
Settings > Account Management > Integrations > API tokens.

Rate limiting and automatic retries are off by default; enable them with
``rate_limiter``/``retry_config`` or use :class:`RateLimitedClient`.
"""

from .auth import X_API_SECRET_HEADER, X_AUTH_TOKEN_HEADER, login
from .client import (
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    DEMO_BASE_URL,
    VERSION,
    Client,
    HTTPResponse,
    RateLimitedClient,
    UrllibTransport,
)
from .clients import ClientsService, ClientListOptions
from .credits import CreditsService, CreditListOptions
from .files import DownloadsService, UploadsService
from .invoices import InvoicesService, InvoiceListOptions
from .payment_terms import PaymentTermsService, PaymentTermListOptions
from .payments import PaymentsService, PaymentListOptions
from .errors import (
    APIError,
    Headers,
    InvoiceNinjaError,
    NetworkError,
    is_api_error,
    parse_api_error,
)
from .models import (
    BulkAction,
    ClientContact,
    ClientPortalSwitchRequest,
    ClientPortalSwitchResponse,
    Credit,
    INClient,
    Invoice,
    LineItem,
    Links,
    ListResponse,
    Meta,
    Model,
    Pagination,
    Payment,
    PaymentCredit,
    PaymentInvoice,
    PaymentRequest,
    PaymentTerm,
    Paymentable,
    RefundRequest,
    StatementRequest,
)
from .retry import (
    RateLimitInfo,
    RateLimiter,
    RetryConfig,
    default_retry_config,
    is_idempotent,
    parse_rate_limit_headers,
    parse_retry_after,
)
from .webhooks import (
    LEGACY_SIGNATURE_HEADER,
    MAX_WEBHOOK_BODY_BYTES,
    SIGNATURE_HEADER,
    WEBHOOK_EVENT_HEADER,
    WEBHOOK_EVENT_QUERY_PARAM,
    WEBHOOK_SECRET_HEADER,
    WebhookEvent,
    WebhookHandler,
)

# requests is imported lazily inside RequestsTransport, keeping the package
# dependency-free; import requests before instantiating it.
from .transports import RequestsTransport

__version__ = VERSION  # single source of truth: invoice_ninja/_version.py

__all__ = [
    "__version__",
    # auth
    "login",
    "X_API_SECRET_HEADER",
    "X_AUTH_TOKEN_HEADER",
    # client
    "Client",
    "RateLimitedClient",
    "HTTPResponse",
    "UrllibTransport",
    "DEFAULT_BASE_URL",
    "DEMO_BASE_URL",
    "DEFAULT_TIMEOUT",
    "VERSION",
    # services
    "PaymentsService",
    "PaymentListOptions",
    "InvoicesService",
    "InvoiceListOptions",
    "ClientsService",
    "ClientListOptions",
    "PaymentTermsService",
    "PaymentTermListOptions",
    "CreditsService",
    "CreditListOptions",
    "DownloadsService",
    "UploadsService",
    # errors
    "APIError",
    "NetworkError",
    "InvoiceNinjaError",
    "Headers",
    "parse_api_error",
    "is_api_error",
    # models
    "Model",
    "Payment",
    "PaymentRequest",
    "PaymentInvoice",
    "PaymentCredit",
    "Paymentable",
    "Invoice",
    "LineItem",
    "INClient",
    "ClientContact",
    "Credit",
    "PaymentTerm",
    "Meta",
    "Pagination",
    "Links",
    "ListResponse",
    "BulkAction",
    "RefundRequest",
    "StatementRequest",
    "ClientPortalSwitchRequest",
    "ClientPortalSwitchResponse",
    # retry
    "RetryConfig",
    "default_retry_config",
    "RateLimiter",
    "RateLimitInfo",
    "parse_rate_limit_headers",
    "parse_retry_after",
    "is_idempotent",
    # webhooks
    "WebhookHandler",
    "WebhookEvent",
    "WEBHOOK_EVENT_HEADER",
    "WEBHOOK_EVENT_QUERY_PARAM",
    "WEBHOOK_SECRET_HEADER",
    "MAX_WEBHOOK_BODY_BYTES",
    "SIGNATURE_HEADER",
    "LEGACY_SIGNATURE_HEADER",
    # optional transports (requests)
    "RequestsTransport",
]
