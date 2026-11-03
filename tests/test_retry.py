"""Tests for retry and rate limiting, ported from retry_test.go."""

import math
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

from invoice_ninja import (
    APIError,
    Client,
    Headers,
    NetworkError,
    PaymentRequest,
    Invoice,
    RateLimiter,
    RateLimitedClient,
    RetryConfig,
    default_retry_config,
    parse_rate_limit_headers,
    parse_retry_after,
)

from .support import FlakyServer, TestServer


def fast_retry_config() -> RetryConfig:
    """A retry configuration with short backoffs for tests."""
    return RetryConfig(
        max_retries=3,
        initial_backoff=0.001,
        max_backoff=0.01,
        backoff_multiplier=2.0,
        retry_on_status_codes=(429, 500, 502, 503, 504),
        jitter=False,
    )


class TestRetryConfig(unittest.TestCase):
    def test_default_retry_config(self):
        config = default_retry_config()
        self.assertEqual(config.max_retries, 3)
        self.assertEqual(config.initial_backoff, 1.0)
        self.assertEqual(config.max_backoff, 30.0)
        self.assertEqual(config.backoff_multiplier, 2.0)
        self.assertTrue(config.jitter)
        self.assertFalse(config.retry_non_idempotent)
        self.assertEqual(tuple(config.retry_on_status_codes), (429, 500, 502, 503, 504))

    def test_should_retry(self):
        config = default_retry_config()
        net_err = NetworkError("request failed", RuntimeError("connection reset"))

        cases = [
            ("rate limited error", "GET", APIError(status_code=429), 0, True),
            ("server error 500", "GET", APIError(status_code=500), 0, True),
            ("server error 503", "GET", APIError(status_code=503), 0, True),
            ("client error 400", "GET", APIError(status_code=400), 0, False),
            ("not found error", "GET", APIError(status_code=404), 0, False),
            ("max retries exceeded", "GET", APIError(status_code=500), 3, False),
            ("network error on GET", "GET", net_err, 0, True),
            ("network error on POST", "POST", net_err, 0, False),
            ("server error on POST", "POST", APIError(status_code=503), 0, False),
            ("rate limited POST", "POST", APIError(status_code=429), 0, True),
            ("server error on PUT", "PUT", APIError(status_code=502), 0, True),
            ("other error", "GET", ValueError("failed to unmarshal response"), 0, False),
        ]
        for name, method, err, attempt, expected in cases:
            with self.subTest(name):
                self.assertEqual(config.should_retry(method, err, attempt), expected)

    def test_should_retry_non_idempotent_enabled(self):
        config = default_retry_config()
        config.retry_non_idempotent = True
        self.assertTrue(config.should_retry("POST", APIError(status_code=503), 0))

    def test_calculate_backoff(self):
        config = default_retry_config()
        config.jitter = False

        cases = [
            ("first attempt", 0, 1.0),
            ("second attempt", 1, 2.0),
            ("third attempt", 2, 4.0),
        ]
        for name, attempt, expected in cases:
            with self.subTest(name):
                result, ok = config.calculate_backoff(attempt, APIError(status_code=500))
                self.assertTrue(ok)
                self.assertEqual(result, expected)

    def test_calculate_backoff_max_cap(self):
        config = default_retry_config()
        config.jitter = False
        config.max_backoff = 5.0

        backoff, ok = config.calculate_backoff(10, APIError(status_code=500))
        self.assertTrue(ok)
        self.assertEqual(backoff, 5.0)

    def test_calculate_backoff_zero_multiplier(self):
        config = RetryConfig(initial_backoff=1.0, backoff_multiplier=0, jitter=False)

        for attempt in range(3):
            backoff, ok = config.calculate_backoff(attempt, APIError(status_code=500))
            self.assertTrue(ok)
            self.assertEqual(backoff, 1.0)

    def test_calculate_backoff_rate_limited(self):
        config = default_retry_config()
        config.jitter = False

        # Without Retry-After, rate limited errors use exponential backoff.
        backoff, ok = config.calculate_backoff(1, APIError(status_code=429))
        self.assertTrue(ok)
        self.assertEqual(backoff, 2.0)

        # Retry-After is honored.
        headers = Headers({"Retry-After": "7"})
        backoff, ok = config.calculate_backoff(0, APIError(status_code=429, headers=headers))
        self.assertTrue(ok)
        self.assertEqual(backoff, 7.0)

        # A Retry-After longer than MaxBackoff stops retrying.
        headers.set("Retry-After", "120")
        _, ok = config.calculate_backoff(0, APIError(status_code=429, headers=headers))
        self.assertFalse(ok)

    def test_parse_retry_after_too_large(self):
        for value in ("9223372037", "99999999999999999999"):
            wait, ok = parse_retry_after(value)
            self.assertTrue(ok, value)
            self.assertEqual(wait, math.inf, value)

        _, ok = parse_retry_after("-99999999999999999999")
        self.assertFalse(ok)

        # A delay too long to represent stops retrying instead of retrying immediately.
        headers = Headers({"Retry-After": "9223372037"})
        _, ok = default_retry_config().calculate_backoff(
            0, APIError(status_code=429, headers=headers)
        )
        self.assertFalse(ok)

    def test_parse_retry_after(self):
        now = datetime(2026, 1, 2, 15, 4, 5, tzinfo=timezone.utc)

        cases = [
            ("empty", "", 0.0, False),
            ("seconds", "5", 5.0, True),
            ("negative seconds", "-1", 0.0, False),
            ("invalid", "soon", 0.0, False),
            ("future date", format_datetime(now + timedelta(seconds=10), usegmt=True), 10.0, True),
            ("past date", format_datetime(now - timedelta(minutes=1), usegmt=True), 0.0, True),
        ]
        for name, value, expected_wait, expected_ok in cases:
            with self.subTest(name):
                result, ok = parse_retry_after(value, now)
                # Date parsing has second-level precision, allow rounding.
                if expected_ok and isinstance(expected_wait, float) and expected_wait > 1:
                    self.assertTrue(ok)
                    self.assertAlmostEqual(result, expected_wait, delta=1.0)
                else:
                    self.assertEqual(result, expected_wait)
                    self.assertEqual(ok, expected_ok)


class TestRateLimiter(unittest.TestCase):
    def test_rate_limiter(self):
        limiter = RateLimiter(5)  # 5 requests per second

        start = time.monotonic()
        for _ in range(5):
            limiter.wait()
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 0.5)

    def test_rate_limiter_concurrent(self):
        limiter = RateLimiter(10)

        results = []
        errors = []

        def worker():
            try:
                limiter.wait()
                results.append(1)
            except Exception as err:  # pragma: no cover - defensive
                errors.append(err)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(results), 10)
        self.assertEqual(errors, [])

    def test_rate_limiter_disabled(self):
        for limit in (0, -1):
            with self.subTest(limit=limit):
                limiter = RateLimiter(limit)
                start = time.monotonic()
                for _ in range(100):
                    limiter.wait()
                self.assertLess(time.monotonic() - start, 1.0)

    def test_rate_limiter_blocks_at_limit(self):
        limiter = RateLimiter(1)
        limiter.wait()
        start = time.monotonic()
        limiter.wait()  # Must wait for the window to free a slot.
        elapsed = time.monotonic() - start
        self.assertGreaterEqual(elapsed, 0.5)


class TestRateLimitedClient(unittest.TestCase):
    def test_new_rate_limited_client(self):
        client = RateLimitedClient("test-token")
        self.assertIsNotNone(client._rate_limiter)
        self.assertIsNotNone(client._retry_config)

    def test_new_rate_limited_client_options_override_defaults(self):
        config = fast_retry_config()
        limiter = RateLimiter(3)

        client = RateLimitedClient("test-token", retry_config=config, rate_limiter=limiter)

        self.assertIs(client._retry_config, config)
        self.assertIs(client._rate_limiter, limiter)

    def test_set_rate_limit(self):
        client = RateLimitedClient("test-token")
        client.set_rate_limit(20)
        self.assertEqual(client._rate_limiter.requests_limit, 20)

    def test_set_retry_config(self):
        client = RateLimitedClient("test-token")
        custom = RetryConfig(max_retries=5, initial_backoff=2.0, max_backoff=60.0)
        client.set_retry_config(custom)
        self.assertEqual(client._retry_config.max_retries, 5)

    def test_parse_rate_limit_headers(self):
        headers = Headers({"X-RateLimit-Limit": "100", "X-RateLimit-Remaining": "95"})
        info = parse_rate_limit_headers(headers)
        self.assertEqual(info.limit, 100)
        self.assertEqual(info.remaining, 95)

    def test_parse_rate_limit_headers_empty(self):
        info = parse_rate_limit_headers(Headers())
        self.assertEqual(info.limit, 0)
        self.assertEqual(info.remaining, 0)


class TestClientRetries(unittest.TestCase):
    def test_rate_limited_client_retries_service_methods(self):
        server = FlakyServer(1, 503, '{"data":[{"id":"abc123"}]}')
        self.addCleanup(server.close)

        client = RateLimitedClient("test-token", base_url=server.url)
        client.set_retry_config(fast_retry_config())

        resp = client.payments.list()
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(server.calls, 2)

    def test_client_with_retry_config_retries_requests(self):
        server = FlakyServer(2, 502, '{"status":"ok"}')
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url, retry_config=fast_retry_config())

        result = client.request("GET", "/test")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(server.calls, 3)

    def test_client_without_retry_config_does_not_retry(self):
        server = FlakyServer(1, 503, "{}")
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        with self.assertRaises(APIError) as ctx:
            client.request("GET", "/test")
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(server.calls, 1)

    def test_retry_does_not_repeat_post_after_server_error(self):
        server = FlakyServer(1, 503, '{"data":{"id":"new123"}}')
        self.addCleanup(server.close)

        client = RateLimitedClient("test-token", base_url=server.url)
        client.set_retry_config(fast_retry_config())

        with self.assertRaises(APIError):
            client.payments.create(PaymentRequest(client_id="client123", amount=10))
        # POST is not retried after a server error.
        self.assertEqual(server.calls, 1)

    def test_retry_repeats_post_after_rate_limit(self):
        server = FlakyServer(1, 429, '{"data":{"id":"new123"}}')
        self.addCleanup(server.close)

        client = RateLimitedClient("test-token", base_url=server.url)
        client.set_retry_config(fast_retry_config())

        payment = client.payments.create(PaymentRequest(client_id="client123", amount=10))
        self.assertEqual(payment.id, "new123")
        self.assertEqual(server.calls, 2)

    def test_retry_stops_when_retry_after_exceeds_max_backoff(self):
        calls = []

        def callback(request):
            calls.append(1)
            return 429, {"Retry-After": "120"}, b""

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url, retry_config=fast_retry_config())

        with self.assertRaises(APIError) as ctx:
            client.request("GET", "/test")

        self.assertTrue(ctx.exception.is_rate_limited())
        self.assertEqual(ctx.exception.headers.get("Retry-After"), "120")
        self.assertEqual(len(calls), 1)

    def test_retry_replays_request_body(self):
        bodies = []
        calls = []

        def callback(request):
            calls.append(1)
            bodies.append(request.body)
            if len(calls) == 1:
                return 503, {}, b""
            return 200, {"Content-Type": "application/json"}, b'{"data":{"id":"inv123"}}'

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = RateLimitedClient("test-token", base_url=server.url)
        client.set_retry_config(fast_retry_config())

        client.invoices.update("inv123", Invoice(po_number="PO-1"))

        self.assertEqual(len(bodies), 2)
        self.assertNotEqual(bodies[0], b"")
        self.assertEqual(bodies[0], bodies[1])

    def test_downloads_retry_server_errors(self):
        server = FlakyServer(1, 503, "%PDF-1.4")
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url, retry_config=fast_retry_config())

        pdf = client.downloads.download_invoice_pdf("inv-key")
        self.assertEqual(pdf, b"%PDF-1.4")
        self.assertEqual(server.calls, 2)

    def test_do_request_with_retry_sends_query(self):
        queries = []

        server = TestServer(lambda request: (queries.append(request.query_get("per_page")), (200, {}, b"{}"))[1])
        self.addCleanup(server.close)

        client = RateLimitedClient("test-token", base_url=server.url)

        for query in (
            {"per_page": ["5"]},
            {"per_page": ("5",)},
            {"per_page": "5"},
        ):
            client.do_request_with_retry("GET", "/api/v1/payments", query)

        self.assertEqual(queries, ["5", "5", "5"])

        with self.assertRaises(TypeError):
            client.do_request_with_retry("GET", "/api/v1/payments", 42)

    def test_do_request_with_retry_negative_max_retries(self):
        server = FlakyServer(100, 500, "{}")
        self.addCleanup(server.close)

        client = RateLimitedClient("test-token", base_url=server.url)
        client.set_retry_config(RetryConfig(max_retries=-1))

        with self.assertRaises(APIError):
            client.do_request_with_retry("GET", "/test")
        self.assertEqual(server.calls, 1)

    def test_rate_limited_client_set_retry_config_none(self):
        server = FlakyServer(1, 503, "{}")
        self.addCleanup(server.close)

        client = RateLimitedClient("test-token", base_url=server.url)
        client.set_retry_config(None)

        with self.assertRaises(APIError):
            client.request("GET", "/test")
        self.assertEqual(server.calls, 1)


if __name__ == "__main__":
    unittest.main()
