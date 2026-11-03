"""Demonstrates obtaining an API token with email and password.

POST /api/v1/login with {"email": ..., "password": ...} returns an API token
in the X-Auth-Token response header (cloud builds may return it in the body
instead; the SDK accepts both). The token is then sent as X-API-TOKEN on
every call.

The login endpoint is rate-limited to a handful of calls per minute, so cache
the token between runs instead of logging in every time.

Run with: python3 examples/login.py
Requires: IN_EMAIL and IN_PASSWORD environment variables.
"""

import os
import sys

from invoice_ninja import Client, InvoiceListOptions, login


def main() -> None:
    email = os.environ.get("IN_EMAIL")
    password = os.environ.get("IN_PASSWORD")
    if not email or not password:
        sys.exit("IN_EMAIL and IN_PASSWORD environment variables are required")

    # Self-hosted? Pass your URL, e.g. login(email, password, "https://your-instance.com").
    # If the server sets API_SECRET, pass api_secret="..." as well.
    print("Logging in...")
    token = login(email, password)
    print(f"Got token: {token[:4]}...{token[-4:]}")
    # Cache the token (e.g. in a file with 0600 permissions) and reuse it;
    # the login endpoint is rate-limited.

    # Build a client with the token and use the API.
    client = Client(token)
    # Or in one step:
    # client = Client.from_login(email, password)

    invoices = client.invoices.list(InvoiceListOptions(per_page=5))
    print(f"Found {len(invoices.data)} invoices")
    for invoice in invoices.data:
        print(f"  - {invoice.number}: ${invoice.amount:.2f} (status {invoice.status_id})")


if __name__ == "__main__":
    main()
