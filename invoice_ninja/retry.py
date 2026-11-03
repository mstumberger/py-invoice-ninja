"""Retry and rate limiting for the Invoice Ninja SDK.

Requests that fail with a network error, or with a status code listed in
:class:`RetryConfig`, are retried up to ``max_retries`` times with exponential
backoff. POST and PATCH requests, such as creating a payment or emailing an
invoice, are only retried after a 429 response unless ``retry_non_idempotent``
is set: after a network or server error the server may already have processed
them.
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Mapping, Optional, Tuple

from .errors import APIError, Headers, NetworkError

__all__ = [
    "RetryConfig",
    "default_retry_config",
    "RateLimiter",
    "RateLimitInfo",
    "parse_rate_limit_headers",
    "parse_retry_after",
    "is_idempotent",
]

#: Rate limit (requests per second) used by RateLimitedClient.
DEFAULT_REQUESTS_PER_SECOND = 10

#: Largest fraction of the backoff added as random jitter.
MAX_JITTER_FRACTION = 0.3

#: Largest number of seconds whose delay fits in a Go time.Duration; larger
#: Retry-After values are treated as an effectively unbounded wait.
_MAX_RETRY_AFTER_SECONDS = 9_223_372_036


@dataclass
class RetryConfig:
    """Configuration for automatic retries of failed API requests.

    Durations are expressed in seconds (floats).
    """

    #: Maximum number of retry attempts. Zero or less disables retries.
    max_retries: int = 3
    #: Initial backoff in seconds.
    initial_backoff: float = 1.0
    #: Maximum backoff in seconds. Zero means no limit. If the Retry-After
    #: header of a 429 response asks for a longer wait, the error is returned
    #: instead of retrying.
    max_backoff: float = 30.0
    #: Multiplier applied to the backoff after each retry. Values of zero or
    #: less are treated as 1.
    backoff_multiplier: float = 2.0
    #: HTTP status codes that should trigger a retry.
    retry_on_status_codes: Tuple[int, ...] = (429, 500, 502, 503, 504)
    #: Add randomness to the backoff to prevent thundering herd.
    jitter: bool = True
    #: Also retry POST and PATCH requests after network errors and server
    #: errors. Only enable if repeating those requests is safe.
    retry_non_idempotent: bool = False

    def should_retry(self, method: str, err: BaseException, attempt: int) -> bool:
        """Report whether a request with *method* that failed with *err* on
        *attempt* (counting from 0) should be retried."""
        if attempt >= self.max_retries:
            return False

        if isinstance(err, NetworkError):
            return self.retry_non_idempotent or is_idempotent(method)

        if not isinstance(err, APIError) or not self.retries_status_code(err.status_code):
            return False

        # A 429 response means the request was rejected without being processed.
        if err.status_code == 429:
            return True

        return self.retry_non_idempotent or is_idempotent(method)

    def retries_status_code(self, status_code: int) -> bool:
        """Report whether *status_code* is listed in retry_on_status_codes."""
        return status_code in self.retry_on_status_codes

    def calculate_backoff(self, attempt: int, err: BaseException) -> Tuple[float, bool]:
        """Return how long to wait (in seconds) before retrying a request that
        failed with *err* on *attempt*. Returns ``(0, False)`` when the server
        asked for a longer wait than ``max_backoff``."""
        # Honor the Retry-After header of 429 responses.
        if isinstance(err, APIError) and err.status_code == 429:
            wait, found = parse_retry_after(err.headers.get("Retry-After"))
            if found:
                if self.max_backoff > 0 and wait > self.max_backoff:
                    return 0, False
                return wait, True

        multiplier = self.backoff_multiplier
        if multiplier <= 0:
            multiplier = 1

        # Exponential backoff.
        backoff = float(self.initial_backoff) * (multiplier ** attempt)

        # Apply jitter.
        if self.jitter:
            backoff += random.random() * MAX_JITTER_FRACTION * backoff

        # Cap at max backoff.
        if self.max_backoff > 0 and backoff > self.max_backoff:
            backoff = self.max_backoff

        return backoff, True


def default_retry_config() -> RetryConfig:
    """Return the default retry configuration."""
    return RetryConfig(
        max_retries=3,
        initial_backoff=1.0,
        max_backoff=30.0,
        backoff_multiplier=2.0,
        retry_on_status_codes=(429, 500, 502, 503, 504),
        jitter=True,
    )


def is_idempotent(method: str) -> bool:
    """Report whether a request with this HTTP method can safely be repeated."""
    return method.upper() in ("GET", "HEAD", "OPTIONS", "TRACE", "PUT", "DELETE")


def parse_retry_after(value: str, now: Optional[datetime] = None) -> Tuple[float, bool]:
    """Parse a Retry-After header value: a number of seconds or an HTTP date.

    Returns ``(seconds, found)``. A delay too long to represent is returned as
    ``math.inf`` so it is never mistaken for a short or negative wait.
    """
    if not value:
        return 0.0, False

    try:
        seconds = int(value)
    except ValueError:
        seconds = None

    if seconds is not None:
        if seconds < 0:
            return 0.0, False
        if seconds > _MAX_RETRY_AFTER_SECONDS:
            # Too many seconds to represent, so wait as long as possible.
            return float("inf"), True
        return float(seconds), True

    date = _parse_http_date(value)
    if date is not None:
        if now is None:
            now = datetime.now(timezone.utc)
        wait = (date - now).total_seconds()
        if wait > 0:
            return wait, True
        return 0.0, True

    return 0.0, False


def _parse_http_date(value: str) -> Optional[datetime]:
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


class RateLimiter:
    """Client-side rate limiting using a sliding one-second window."""

    def __init__(self, requests_per_second: int) -> None:
        """Create a rate limiter allowing *requests_per_second* requests per
        second. A value of zero or less disables rate limiting."""
        if requests_per_second < 0:
            requests_per_second = 0
        self.requests_limit = requests_per_second
        self.window_size = 1.0
        self._mu = threading.Lock()
        self._requests: list[float] = []

    def wait(self) -> None:
        """Block until a request is allowed under the rate limit."""
        if self.requests_limit <= 0:
            return

        while True:
            with self._mu:
                now = time.monotonic()

                # Remove expired requests from the window.
                cutoff = now - self.window_size
                self._requests = [t for t in self._requests if t > cutoff]

                # Check if we're at the limit.
                if len(self._requests) >= self.requests_limit:
                    # Wait until the oldest request expires.
                    wait_time = self._requests[0] + self.window_size - now
                else:
                    # Record this request and return.
                    self._requests.append(now)
                    return

            if wait_time > 0:
                time.sleep(wait_time)


@dataclass
class RateLimitInfo:
    """Rate limit information from API response headers."""

    #: Maximum number of requests allowed per window.
    limit: int = 0
    #: Requests remaining in the current window.
    remaining: int = 0
    #: Time when the rate limit window resets, if provided.
    reset: Optional[datetime] = None


def parse_rate_limit_headers(headers: Headers | Mapping[str, str]) -> RateLimitInfo:
    """Parse rate limit information from HTTP response headers, such as
    ``APIError.headers``."""
    if not isinstance(headers, Headers):
        headers = Headers(headers)

    info = RateLimitInfo()

    limit = headers.get("X-RateLimit-Limit")
    if limit:
        try:
            info.limit = int(limit)
        except ValueError:
            pass

    remaining = headers.get("X-RateLimit-Remaining")
    if remaining:
        try:
            info.remaining = int(remaining)
        except ValueError:
            pass

    # Note: Invoice Ninja may not provide a reset timestamp.
    # This is a placeholder for when it does.
    reset = headers.get("X-RateLimit-Reset")
    if reset:
        try:
            info.reset = datetime.fromtimestamp(int(reset), tz=timezone.utc)
        except ValueError:
            pass

    return info
