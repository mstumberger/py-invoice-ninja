"""Demonstrates creating and managing invoices.

This example shows how to:
- Create an invoice with line items
- Get the invoice details
- Update the invoice's public notes

Requires the INVOICE_NINJA_TOKEN and INVOICE_NINJA_CLIENT_ID environment variables.

Run with: python3 examples/invoices.py
"""

import os
import sys
from datetime import date, timedelta

from invoice_ninja import Client, Invoice, LineItem


def main() -> None:
    token = os.environ.get("INVOICE_NINJA_TOKEN")
    if not token:
        sys.exit("INVOICE_NINJA_TOKEN environment variable is required")

    client_id = os.environ.get("INVOICE_NINJA_CLIENT_ID")
    if not client_id:
        sys.exit("INVOICE_NINJA_CLIENT_ID environment variable is required")

    client = Client(token)

    # Create an invoice with line items.
    print("=== Creating Invoice ===")
    invoice = client.invoices.create(
        Invoice(
            client_id=client_id,
            date=date.today().isoformat(),
            due_date=(date.today() + timedelta(days=30)).isoformat(),
            line_items=[
                LineItem(product_key="Consulting", notes="Professional consulting services",
                         quantity=10, cost=150.00),
                LineItem(product_key="Development", notes="Custom software development",
                         quantity=20, cost=125.00),
                LineItem(product_key="Support", notes="Technical support hours",
                         quantity=5, cost=75.00),
            ],
            public_notes="Thank you for your business!",
            terms="Payment due within 30 days",
            footer="Please make checks payable to Acme Corp",
        )
    )
    print(f"Created invoice: {invoice.number}")
    print(f"  Amount: ${invoice.amount:.2f}")
    print(f"  Balance: ${invoice.balance:.2f}")

    # Get the invoice details.
    print("\n=== Getting Invoice Details ===")
    inv = client.invoices.get(invoice.id)
    print(f"Invoice {inv.number} details:")
    print(f"  Client ID: {inv.client_id}")
    print(f"  Date: {inv.date}")
    print(f"  Due Date: {inv.due_date}")
    print(f"  Status: {inv.status_id}")
    print(f"  Line Items: {len(inv.line_items)}")

    # Update the invoice.
    print("\n=== Updating Invoice ===")
    inv.public_notes = "Thank you for choosing our services!"
    updated = client.invoices.update(inv.id, inv)
    print(f"Updated invoice notes: {updated.public_notes}")

    print("\nInvoice example completed successfully!")


if __name__ == "__main__":
    main()
