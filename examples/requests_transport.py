"""Demonstrates using the SDK with the requests library as the HTTP transport.

The default transport is stdlib urllib (zero dependencies). When your project
already uses requests, plug it in via RequestsTransport to share its Session
(connection pooling, proxies, retries, instrumentation).

Install the optional dependency first:

    pip install requests

Run with: python3 examples/requests_transport.py
Requires: INVOICE_NINJA_TOKEN (or INVOICE_NINJA_EMAIL + INVOICE_NINJA_PASSWORD).
Optional: INVOICE_NINJA_BASE_URL for self-hosted instances.
"""

import os
import sys
from pathlib import Path

# Run from a repo checkout without installing; unnecessary after pip install .
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from invoice_ninja import Client, PaymentListOptions, login
from invoice_ninja.transports import RequestsTransport


def main() -> None:
    token = os.environ.get("INVOICE_NINJA_TOKEN")
    base_url = os.environ.get("INVOICE_NINJA_BASE_URL") or None

    # One transport (one requests.Session) can serve both the login call and
    # every API request afterwards.
    transport = RequestsTransport()

    if not token:
        email = os.environ.get("INVOICE_NINJA_EMAIL")
        password = os.environ.get("INVOICE_NINJA_PASSWORD")
        if not (email and password):
            sys.exit(
                "Set INVOICE_NINJA_TOKEN, or INVOICE_NINJA_EMAIL and "
                "INVOICE_NINJA_PASSWORD"
            )
        token = login(email, password, base_url or "https://invoicing.co",
                      http_client=transport)
        print(f"Logged in, got token: {token[:4]}...{token[-4:]}")

    client = Client(token, base_url=base_url, http_client=transport)

    payments = client.payments.list(PaymentListOptions(per_page=5))
    print(f"Found {len(payments.data)} payments")
    for payment in payments.data:
        print(f"  - Payment {payment.number}: ${payment.amount:.2f}")

    transport.close()


if __name__ == "__main__":
    main()
