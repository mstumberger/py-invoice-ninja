"""Error types for the Invoice Ninja SDK.

The API raises :class:`APIError` for HTTP-level error responses (status >= 400)
and :class:`NetworkError` when a request could not be sent or its response
could not be read. Both derive from :class:`InvoiceNinjaError` so callers can
catch every SDK failure with a single except clause.
"""

from __future__ import annotations

import json
from typing import Iterable, Mapping, Optional, Tuple

__all__ = [
    "Headers",
    "InvoiceNinjaError",
    "APIError",
    "NetworkError",
    "parse_api_error",
    "is_api_error",
]


class Headers:
    """A read-mostly, case-insensitive HTTP header mapping.

    Mirrors Go's ``http.Header.Get`` behaviour: looking up a header is
    case-insensitive and a missing header yields an empty string.
    """

    def __init__(self, data: Optional[Mapping[str, str] | Iterable[Tuple[str, str]]] = None) -> None:
        self._headers: dict[str, str] = {}
        if data is None:
            return
        items = data.items() if hasattr(data, "items") else data
        for name, value in items:
            if value is None:
                continue
            self._headers[name.lower()] = str(value)

    def get(self, name: str, default: str = "") -> str:
        """Return the first value for *name*, or *default* if absent."""
        return self._headers.get(name.lower(), default)

    def set(self, name: str, value: str) -> None:
        self._headers[name.lower()] = value

    def __contains__(self, name: str) -> bool:
        return name.lower() in self._headers

    def __iter__(self):
        return iter(self._headers.items())

    def __len__(self) -> int:
        return len(self._headers)

    def __repr__(self) -> str:
        return f"Headers({self._headers!r})"


class InvoiceNinjaError(Exception):
    """Base class for all errors raised by this SDK."""


class APIError(InvoiceNinjaError):
    """An error response returned by the Invoice Ninja API."""

    def __init__(
        self,
        status_code: int = 0,
        message: str = "",
        errors: Optional[Mapping[str, list[str]]] = None,
        headers: Optional[Headers] = None,
    ) -> None:
        super().__init__(message)
        #: HTTP status code of the response.
        self.status_code = status_code
        #: Human-readable error message from the API, or a default message.
        self.message = message
        #: Field-specific validation errors, e.g. ``{"email": ["Email is required"]}``.
        self.errors: dict[str, list[str]] = dict(errors) if errors else {}
        #: Response headers, such as ``Retry-After`` on 429 responses.
        self.headers = headers if headers is not None else Headers()

    def __str__(self) -> str:
        if self.message:
            return f"Invoice Ninja API error (status {self.status_code}): {self.message}"
        return f"Invoice Ninja API error (status {self.status_code})"

    def is_not_found(self) -> bool:
        """Return True for a 404 Not Found response."""
        return self.status_code == 404

    def is_unauthorized(self) -> bool:
        """Return True for a 401 Unauthorized response."""
        return self.status_code == 401

    def is_forbidden(self) -> bool:
        """Return True for a 403 Forbidden response."""
        return self.status_code == 403

    def is_validation_error(self) -> bool:
        """Return True for a 422 Unprocessable Entity response."""
        return self.status_code == 422

    def is_rate_limited(self) -> bool:
        """Return True for a 429 Too Many Requests response."""
        return self.status_code == 429

    def is_server_error(self) -> bool:
        """Return True for a 5xx server error response."""
        return self.status_code >= 500


class NetworkError(InvoiceNinjaError):
    """A request could not be sent, or its response could not be read."""

    def __init__(self, op: str, err: BaseException) -> None:
        super().__init__(f"{op}: {err}")
        #: Short description of the failed operation, e.g. ``"request failed"``.
        self.op = op
        #: The underlying exception.
        self.err = err

    @property
    def cause(self) -> BaseException:
        """The underlying exception (alias for ``__cause__`` style access)."""
        return self.err

    def __str__(self) -> str:
        return f"{self.op}: {self.err}"


def parse_api_error(status_code: int, body: bytes, headers: Optional[Headers] = None) -> APIError:
    """Parse an API error response body into an :class:`APIError`.

    Unknown status codes without a parsable message keep an empty message,
    and common status codes receive a default message, mirroring the Go SDK.
    """
    api_error = APIError(status_code=status_code, headers=headers)

    if body:
        try:
            error_response = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            error_response = None
        if isinstance(error_response, dict):
            message = error_response.get("message")
            if isinstance(message, str):
                api_error.message = message
            errors = error_response.get("errors")
            if isinstance(errors, dict):
                api_error.errors = {
                    str(field): list(messages) if isinstance(messages, (list, tuple)) else [str(messages)]
                    for field, messages in errors.items()
                }

    if api_error.message == "":
        if status_code == 400:
            api_error.message = "bad request"
        elif status_code == 401:
            api_error.message = "unauthorized - check your API token"
        elif status_code == 403:
            api_error.message = "forbidden - you don't have permission to access this resource"
        elif status_code == 404:
            api_error.message = "resource not found"
        elif status_code == 422:
            api_error.message = "validation error"
        elif status_code == 429:
            api_error.message = "rate limit exceeded"
        elif status_code >= 500:
            api_error.message = "server error"

    return api_error


def is_api_error(err: Optional[BaseException]) -> Optional[APIError]:
    """Return *err* if it is an :class:`APIError`, otherwise ``None``."""
    if isinstance(err, APIError):
        return err
    return None
