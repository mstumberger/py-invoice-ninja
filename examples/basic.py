"""Demonstrates basic usage of the Invoice Ninja SDK.

This example shows how to:
- Create a client with configuration options
- List payments, invoices and clients with pagination
- Handle errors properly

Run with: python3 examples/basic.py
Requires: INVOICE_NINJA_TOKEN environment variable.
"""

import os
import sys

from invoice_ninja import (
    Client,
    ClientListOptions,
    InvoiceListOptions,
    PaymentListOptions,
    is_api_error,
)


def main() -> None:
    token = os.environ.get("INVOICE_NINJA_TOKEN")
    if not token:
        sys.exit("INVOICE_NINJA_TOKEN environment variable is required")

    # Create a new client with options.
    client = Client(
        token,
        timeout=30,
        # Uncomment for self-hosted instances:
        # base_url="https://your-instance.com",
    )

    # Example 1: List payments.
    print("=== Listing Payments ===")
    try:
        payments = client.payments.list(PaymentListOptions(per_page=5, page=1))
    except Exception as err:
        api_err = is_api_error(err)
        if api_err is not None:
            if api_err.is_unauthorized():
                sys.exit("Invalid API token")
            if api_err.is_rate_limited():
                sys.exit("Rate limited, try again later")
            sys.exit(f"API error: {api_err}")
        sys.exit(f"Error listing payments: {err}")

    print(f"Found {len(payments.data)} payments")
    for payment in payments.data:
        print(f"  - Payment {payment.number}: ${payment.amount:.2f} (Client: {payment.client_id})")

    # Example 2: List invoices.
    print("\n=== Listing Invoices ===")
    invoices = client.invoices.list(InvoiceListOptions(per_page=5, page=1))
    print(f"Found {len(invoices.data)} invoices")
    for invoice in invoices.data:
        print(f"  - Invoice {invoice.number}: ${invoice.amount:.2f} (Status: {invoice.status_id})")

    # Example 3: List clients.
    print("\n=== Listing Clients ===")
    clients = client.clients.list(ClientListOptions(per_page=5, page=1))
    print(f"Found {len(clients.data)} clients")
    for c in clients.data:
        print(f"  - Client {c.number}: {c.name}")

    print("\nBasic example completed successfully!")


if __name__ == "__main__":
    main()
