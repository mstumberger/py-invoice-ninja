"""Email/password login for the Invoice Ninja SDK.

Obtaining an API token with email and password
(https://invoiceninja.github.io/docs/developer-guide/api/authentication):

``POST /api/v1/login`` with a JSON body of ``{"email": ..., "password": ...}``
and the ``X-Requested-With: XMLHttpRequest`` header authenticates against
Invoice Ninja and returns an API token in the ``X-Auth-Token`` response
header. Current cloud builds may instead return the CompanyToken inside the
response body (``data[].token``, a string or an object with a ``token``
field), so all of these are accepted. The returned token is then sent as
``X-API-TOKEN`` on every SDK call.

The login endpoint is rate-limited to a handful of calls per minute, so cache
the token and reuse it instead of logging in for every request.

An optional ``X-API-SECRET`` header can be sent when the server's ``API_SECRET``
environment variable is set.
"""

from __future__ import annotations

import json
import urllib.error
from typing import Any, Mapping, Optional

from .client import DEFAULT_BASE_URL, DEFAULT_TIMEOUT, VERSION, UrllibTransport
from .errors import (
    APIError,
    Headers,
    InvoiceNinjaError,
    NetworkError,
    parse_api_error,
)

__all__ = [
    "login",
    "X_API_SECRET_HEADER",
    "X_AUTH_TOKEN_HEADER",
]

#: Optional request header whose value must match the server's API_SECRET.
X_API_SECRET_HEADER = "X-API-SECRET"

#: Response header carrying the API token on a successful login.
X_AUTH_TOKEN_HEADER = "X-Auth-Token"


def login(
    email: str,
    password: str,
    base_url: str = DEFAULT_BASE_URL,
    *,
    api_secret: str = "",
    timeout: Optional[float] = DEFAULT_TIMEOUT,
    http_client: Optional[Any] = None,
) -> str:
    """Log in with *email* and *password* and return an API token.

    The token is read from the ``X-Auth-Token`` response header, falling back
    to the response body (``token`` field, or ``data[].token`` entries where
    the value may be a string or an object with a ``token`` field).

    Raises :class:`APIError` for HTTP error responses (e.g. 401 for wrong
    credentials), :class:`NetworkError` when the server cannot be reached, and
    :class:`InvoiceNinjaError` when the login succeeds but no token is
    returned.

    :param email: Invoice Ninja account email.
    :param password: Invoice Ninja account password.
    :param base_url: API base URL (cloud or self-hosted).
    :param api_secret: optional value for the ``X-API-SECRET`` header, needed
        when the server sets ``API_SECRET``.
    :param timeout: request timeout in seconds.
    :param http_client: custom transport, see :class:`UrllibTransport`.
    """
    if not email or not password:
        raise ValueError("email and password are required")

    transport = http_client if http_client is not None else UrllibTransport()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": f"py-invoice-ninja/{VERSION}",
    }
    if api_secret:
        headers[X_API_SECRET_HEADER] = api_secret

    body = json.dumps({"email": email, "password": password}).encode("utf-8")

    try:
        response = transport.request(
            "POST",
            f"{base_url.rstrip('/')}/api/v1/login",
            headers,
            body,
            timeout,
        )
    except (urllib.error.URLError, OSError) as err:
        raise NetworkError("request failed", err) from err

    if response.status_code >= 400:
        raise parse_api_error(response.status_code, response.data, response.headers)

    token = _extract_token(response.headers, response.data)
    if not token:
        raise InvoiceNinjaError("Invoice Ninja login succeeded but returned no token")
    return token


def _extract_token(headers: Headers, data: bytes) -> str:
    """Extract the API token from a login response, in priority order:
    the X-Auth-Token header, then the body's token field, then the
    data[].token entries (string, or object with a token field)."""
    token = headers.get(X_AUTH_TOKEN_HEADER)
    if token:
        return token

    if not data:
        return ""
    try:
        body = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return ""

    if not isinstance(body, Mapping):
        return ""

    body_token = body.get("token")
    if isinstance(body_token, str) and body_token:
        return body_token

    entries = body.get("data") or []
    if isinstance(entries, Mapping):
        entries = [entries]
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        company_token = entry.get("token")
        if isinstance(company_token, str) and company_token:
            return company_token
        if isinstance(company_token, Mapping):
            inner = company_token.get("token")
            if isinstance(inner, str) and inner:
                return inner

    return ""
