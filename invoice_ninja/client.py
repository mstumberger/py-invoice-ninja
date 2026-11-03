"""The Invoice Ninja API client.

The client supports both cloud-hosted (invoicing.co) and self-hosted Invoice
Ninja instances. Rate limiting and automatic retries are off by default; pass
``rate_limiter`` and ``retry_config``, or use :class:`RateLimitedClient`::

    from invoice_ninja import Client, RateLimiter, default_retry_config

    client = Client(
        "your-api-token",
        rate_limiter=RateLimiter(10),
        retry_config=default_retry_config(),
    )
    payments = client.payments.list()
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence, Tuple, Union

from .errors import Headers, InvoiceNinjaError, NetworkError, parse_api_error
from .models import Model
from .retry import DEFAULT_REQUESTS_PER_SECOND, RateLimiter, RetryConfig, default_retry_config

__all__ = [
    "Client",
    "RateLimitedClient",
    "HTTPResponse",
    "UrllibTransport",
    "DEFAULT_BASE_URL",
    "DEMO_BASE_URL",
    "DEFAULT_TIMEOUT",
    "VERSION",
]

#: Production Invoice Ninja cloud API endpoint.
DEFAULT_BASE_URL = "https://invoicing.co"

#: Demo Invoice Ninja API endpoint.
DEMO_BASE_URL = "https://demo.invoiceninja.com"

#: Default HTTP timeout in seconds.
DEFAULT_TIMEOUT = 30.0

#: SDK version.
VERSION = "1.0.0"

_JSON_MEDIA_TYPE = "application/json"

QueryValue = Union[
    None,
    Mapping[str, str],
    Mapping[str, Sequence[str]],
    Sequence[Tuple[str, str]],
]


@dataclass
class HTTPResponse:
    """A minimal HTTP response returned by a transport."""

    status_code: int
    headers: Headers
    data: bytes


class UrllibTransport:
    """Default transport that performs HTTP requests with urllib.

    A transport is any object with a ``request(method, url, headers, body,
    timeout)`` method returning an :class:`HTTPResponse` and raising
    ``OSError``/``URLError`` on connection failures. Pass a custom
    implementation as ``http_client`` to reuse an existing HTTP stack.
    """

    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: Optional[bytes],
        timeout: Optional[float],
    ) -> HTTPResponse:
        request = urllib.request.Request(url, data=body, method=method.upper())
        for name, value in headers.items():
            request.add_header(name, value)
        try:
            response = urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as err:
            # HTTPError carries the error response, so surface it as a response.
            try:
                return HTTPResponse(err.code, Headers(err.headers.items()), err.read())
            finally:
                err.close()

        with response:
            data = response.read()
            return HTTPResponse(response.status, Headers(response.headers.items()), data)


@dataclass
class _APIRequest:
    """An HTTP request description. The body is kept as bytes so the request
    can be retried."""

    method: str
    url: str
    body: Optional[bytes] = None
    content_type: str = _JSON_MEDIA_TYPE
    accept: str = _JSON_MEDIA_TYPE


class Client:
    """The Invoice Ninja API client."""

    def __init__(
        self,
        api_token: str,
        *,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        http_client: Optional[Any] = None,
        rate_limiter: Optional[RateLimiter] = None,
        retry_config: Optional[RetryConfig] = None,
    ) -> None:
        """Create a new Invoice Ninja API client.

        :param api_token: API token from Settings > Account Management >
            Integrations > API tokens.
        :param base_url: custom base URL for self-hosted instances.
        :param timeout: request timeout in seconds. When ``http_client`` is
            given and ``timeout`` is None, the custom client keeps its own
            timeout behaviour.
        :param http_client: custom transport, see :class:`UrllibTransport`.
        :param rate_limiter: client-side rate limiter; None disables limiting.
        :param retry_config: retry configuration; None disables retries.
        """
        if http_client is not None:
            # A custom client keeps its own timeout unless one is given here.
            self._http = http_client
            self._timeout = timeout
        else:
            self._http = UrllibTransport()
            self._timeout = DEFAULT_TIMEOUT if timeout is None else timeout

        self.base_url = (base_url if base_url is not None else DEFAULT_BASE_URL).rstrip("/")
        self.api_token = api_token

        self._mu = threading.RLock()
        self._rate_limiter = rate_limiter
        self._retry_config = retry_config

        # Initialize services.
        from .clients import ClientsService
        from .credits import CreditsService
        from .files import DownloadsService, UploadsService
        from .invoices import InvoicesService
        from .payment_terms import PaymentTermsService
        from .payments import PaymentsService

        #: Access to payment-related endpoints.
        self.payments = PaymentsService(self)
        #: Access to invoice-related endpoints.
        self.invoices = InvoicesService(self)
        #: Access to client-related endpoints.
        self.clients = ClientsService(self)
        #: Access to payment terms endpoints.
        self.payment_terms = PaymentTermsService(self)
        #: Access to credit-related endpoints.
        self.credits = CreditsService(self)
        #: Access to file download operations.
        self.downloads = DownloadsService(self)
        #: Access to file upload operations.
        self.uploads = UploadsService(self)

    def set_base_url(self, base_url: str) -> None:
        """Set the API base URL. Use this for self-hosted instances."""
        self.base_url = base_url.rstrip("/")

    @classmethod
    def from_login(
        cls,
        email: str,
        password: str,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ) -> "Client":
        """Create a client by logging in with *email* and *password*.

        Calls :func:`invoice_ninja.auth.login` to obtain an API token, then
        builds an authenticated client. Extra keyword arguments (timeout,
        rate_limiter, retry_config, http_client) are passed to the
        constructor. The login endpoint is rate-limited, so prefer reusing an
        existing token over logging in repeatedly.
        """
        from .auth import login

        token = login(email, password, base_url or DEFAULT_BASE_URL)
        return cls(token, base_url=base_url, **kwargs)

    # ------------------------------------------------------------------
    # Generic requests
    # ------------------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        body: Any = None,
        result_type: Optional[Callable[[Any], Any]] = None,
    ) -> Any:
        """Perform a generic API request against any endpoint.

        :param method: HTTP method, e.g. ``"GET"``.
        :param path: API path, e.g. ``"/api/v1/activities"``.
        :param body: JSON-serializable request body (dict, Model, list, ...).
        :param result_type: optional callable applied to the parsed JSON
            response, e.g. a ``Model.from_dict`` classmethod. By default the
            parsed JSON is returned.
        """
        return self._do_request(method, path, None, body, result_type)

    def request_with_query(
        self,
        method: str,
        path: str,
        query: QueryValue,
        body: Any = None,
        result_type: Optional[Callable[[Any], Any]] = None,
    ) -> Any:
        """Perform a generic API request with query parameters."""
        return self._do_request(method, path, query, body, result_type)

    # ------------------------------------------------------------------
    # Request pipeline
    # ------------------------------------------------------------------

    def _do_request(
        self,
        method: str,
        path: str,
        query: QueryValue,
        body: Any,
        result_type: Optional[Callable[[Any], Any]],
    ) -> Any:
        try:
            split = urllib.parse.urlsplit(self.base_url + path)
        except ValueError as err:
            raise ValueError(f"invalid URL: {err}") from err

        encoded_query = _encode_query(query)
        url = urllib.parse.urlunsplit(
            (split.scheme, split.netloc, split.path, encoded_query, split.fragment)
        )

        api_request = _APIRequest(method=method.upper(), url=url)

        if body is not None:
            if isinstance(body, Model):
                payload: Any = body.to_dict()
            else:
                payload = body
            try:
                api_request.body = json.dumps(payload).encode("utf-8")
            except (TypeError, ValueError) as err:
                raise ValueError(f"failed to marshal request body: {err}") from err

        response_body = self._execute(api_request)

        if not response_body:
            return None

        try:
            parsed = json.loads(response_body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as err:
            raise ValueError(f"failed to unmarshal response: {err}") from err

        if result_type is not None:
            return result_type(parsed)
        return parsed

    def _execute(self, api_request: _APIRequest) -> bytes:
        """Send *api_request*, waiting for the rate limiter before each
        attempt and retrying failed attempts per the retry configuration."""
        limiter, retry_config = self._request_policy()

        attempt = 0
        while True:
            if limiter is not None:
                limiter.wait()

            try:
                return self._send(api_request)
            except InvoiceNinjaError as err:
                if retry_config is None or not retry_config.should_retry(
                    api_request.method, err, attempt
                ):
                    raise
                backoff, ok = retry_config.calculate_backoff(attempt, err)
                if not ok:
                    raise
                time.sleep(backoff)
                attempt += 1

    def _send(self, api_request: _APIRequest) -> bytes:
        """Perform a single HTTP request and return the response body."""
        headers = {
            "X-API-TOKEN": self.api_token,
            "X-Requested-With": "XMLHttpRequest",
        }
        if api_request.content_type:
            headers["Content-Type"] = api_request.content_type
        headers["Accept"] = api_request.accept
        headers["User-Agent"] = f"py-invoice-ninja/{VERSION}"

        try:
            response = self._http.request(
                api_request.method, api_request.url, headers, api_request.body, self._timeout
            )
        except (urllib.error.URLError, OSError) as err:
            raise NetworkError("request failed", err) from err

        if response.status_code >= 400:
            raise parse_api_error(response.status_code, response.data, response.headers)

        return response.data

    def _request_policy(self) -> Tuple[Optional[RateLimiter], Optional[RetryConfig]]:
        with self._mu:
            return self._rate_limiter, self._retry_config


def _encode_query(query: QueryValue) -> str:
    """Encode supported query parameter types into a query string.

    Keys are sorted, mirroring Go's ``url.Values.Encode``.
    """
    if query is None:
        return ""

    if isinstance(query, Mapping):
        pairs: list[Tuple[str, str]] = []
        for key, value in query.items():
            if isinstance(value, str) or not isinstance(value, (list, tuple)):
                pairs.append((str(key), str(value)))
            else:
                pairs.extend((str(key), str(item)) for item in value)
    else:
        pairs = [(str(key), str(value)) for key, value in query]

    pairs.sort()
    return urllib.parse.urlencode(pairs)


class RateLimitedClient(Client):
    """A :class:`Client` with rate limiting and automatic retries enabled.

    It sends at most 10 requests per second and retries failed requests with
    ``default_retry_config()``. Pass ``rate_limiter`` or ``retry_config`` to
    use other settings.
    """

    def __init__(
        self,
        api_token: str,
        *,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        http_client: Optional[Any] = None,
        rate_limiter: Optional[RateLimiter] = None,
        retry_config: Optional[RetryConfig] = None,
    ) -> None:
        # Defaults come first so explicit arguments can override them.
        if rate_limiter is None:
            rate_limiter = RateLimiter(DEFAULT_REQUESTS_PER_SECOND)
        if retry_config is None:
            retry_config = default_retry_config()
        super().__init__(
            api_token,
            base_url=base_url,
            timeout=timeout,
            http_client=http_client,
            rate_limiter=rate_limiter,
            retry_config=retry_config,
        )

    def set_rate_limit(self, requests_per_second: int) -> None:
        """Set the rate limit for API requests.

        A value of zero or less disables rate limiting.
        """
        limiter = RateLimiter(requests_per_second)
        with self._mu:
            self._rate_limiter = limiter

    def set_retry_config(self, config: Optional[RetryConfig]) -> None:
        """Set the retry configuration. None disables retries."""
        with self._mu:
            self._retry_config = config

    def do_request_with_retry(
        self,
        method: str,
        path: str,
        query: QueryValue = None,
        body: Any = None,
        result_type: Optional[Callable[[Any], Any]] = None,
    ) -> Any:
        """Perform a generic API request with rate limiting and retries.

        *query* may be None, a dict of single values, a dict of value lists,
        or a sequence of (key, value) pairs. Other types raise TypeError.
        """
        if query is not None and not isinstance(query, Mapping) and not isinstance(query, (list, tuple)):
            raise TypeError(f"unsupported query type {type(query).__name__}: use a dict or pairs")

        return self._do_request(method, path, query, body, result_type)
