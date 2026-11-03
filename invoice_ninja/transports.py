"""Optional HTTP transports.

The SDK ships with :class:`~invoice_ninja.UrllibTransport` (stdlib, zero
dependencies). :class:`RequestsTransport` adapts the `requests
<https://requests.readthedocs.io>`_ library when you prefer its connection
pooling, retry machinery or instrumentation. requests is imported lazily, so
the SDK stays dependency-free unless you actually use the adapter::

    pip install requests

    from invoice_ninja import Client
    from invoice_ninja.transports import RequestsTransport

    transport = RequestsTransport()          # wraps a requests.Session
    client = Client("your-api-token", http_client=transport)
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from .client import HTTPResponse
from .errors import Headers

__all__ = ["RequestsTransport"]


class RequestsTransport:
    """Transport that performs the SDK's HTTP requests via requests.

    Any transport works: an object with a ``request(method, url, headers,
    body, timeout)`` method returning an :class:`HTTPResponse` and raising
    ``OSError`` on connection failures (requests' exceptions derive from
    ``IOError``, so they map to :class:`~invoice_ninja.NetworkError`
    automatically).
    """

    def __init__(self, session: Optional[Any] = None) -> None:
        """Create the adapter; pass an existing ``requests.Session`` to share
        its connection pool and configuration, or None to create one."""
        try:
            import requests
        except ImportError as err:  # pragma: no cover - depends on environment
            raise ImportError(
                "RequestsTransport requires the requests library; "
                "install it with 'pip install requests'"
            ) from err

        self.session = session if session is not None else requests.Session()

    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: Optional[bytes],
        timeout: Optional[float],
    ) -> HTTPResponse:
        response = self.session.request(
            method,
            url,
            headers=dict(headers),
            data=body,
            timeout=timeout,
        )
        return HTTPResponse(
            response.status_code, Headers(response.headers.items()), response.content
        )

    def close(self) -> None:
        """Close the underlying session."""
        self.session.close()
