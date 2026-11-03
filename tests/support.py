"""Shared test helpers: a local HTTP test server mirroring Go's httptest."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Dict, List, Tuple
from urllib.parse import parse_qs, urlsplit

from invoice_ninja.errors import Headers

Response = Tuple[int, Dict[str, str], bytes]


@dataclass
class RecordedRequest:
    """An incoming request recorded by TestServer."""

    method: str
    target: str
    headers: Dict[str, str]
    body: bytes = b""

    @property
    def path(self) -> str:
        return urlsplit(self.target).path

    @property
    def query(self) -> Dict[str, List[str]]:
        return parse_qs(urlsplit(self.target).query)

    def query_get(self, name: str, default: str = "") -> str:
        values = self.query.get(name, [])
        return values[0] if values else default

    def header(self, name: str, default: str = "") -> str:
        return Headers(self.headers).get(name, default)


class _Handler(BaseHTTPRequestHandler):
    def _handle(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        request = RecordedRequest(
            method=self.command,
            target=self.path,
            headers={k: v for k, v in self.headers.items()},
            body=body,
        )
        status, response_headers, response_body = self.server.callback(request)
        self.send_response(status)
        for name, value in (response_headers or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        if response_body:
            self.wfile.write(response_body)

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_DELETE = _handle
    do_PATCH = _handle
    do_HEAD = _handle
    do_OPTIONS = _handle

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        pass


class TestServer:
    """An HTTP server on 127.0.0.1 with a random port that serves responses
    produced by *callback*. Use ``.url`` as the client base URL."""

    def __init__(self, callback: Callable[[RecordedRequest], Response]) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.server.callback = callback  # type: ignore[attr-defined]
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )
        self.thread.start()

    @property
    def url(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class FlakyServer:
    """A server that responds with *fail_status* to the first *failures*
    requests and with *success_body* afterwards."""

    def __init__(self, failures: int, fail_status: int, success_body: str) -> None:
        self.failures = failures
        self.fail_status = fail_status
        self.success_body = success_body
        self._mu = threading.Lock()
        self.calls = 0
        self.requests: List[RecordedRequest] = []
        self._server = TestServer(self._handle)

    @property
    def url(self) -> str:
        return self._server.url

    def _handle(self, request: RecordedRequest) -> Response:
        with self._mu:
            self.calls += 1
            count = self.calls
            self.requests.append(request)
        if count <= self.failures:
            return self.fail_status, {}, b""
        return 200, {"Content-Type": "application/json"}, self.success_body.encode("utf-8")

    def close(self) -> None:
        self._server.close()
