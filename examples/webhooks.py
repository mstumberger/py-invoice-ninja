"""Demonstrates webhook handling.

This example shows how to:
- Set up a webhook endpoint
- Protect it with a shared secret header
- Register event handlers
- Handle different webhook events

In Invoice Ninja (Settings > Account Management > Integrations > API Webhooks),
create one webhook per event. Name the event in the target URL, for example
https://your-server.com:8080/webhook?event=payment.created, and add an
X-Webhook-Secret header with the value of INVOICE_NINJA_WEBHOOK_SECRET.

Run with: python3 examples/webhooks.py
Requires: INVOICE_NINJA_WEBHOOK_SECRET environment variable.
"""

import os
import sys
from wsgiref.simple_server import make_server

from invoice_ninja import WebhookHandler


def main() -> None:
    secret = os.environ.get("INVOICE_NINJA_WEBHOOK_SECRET", "")
    if not secret:
        sys.exit("INVOICE_NINJA_WEBHOOK_SECRET environment variable is required")

    # Create a webhook handler that requires the X-Webhook-Secret header.
    handler = WebhookHandler(secret)

    # Register event handlers.
    def on_payment_created(event):
        payment = event.parse_payment()
        print(f"New payment: {payment.number} (${payment.amount:.2f})")

    def on_invoice_created(event):
        invoice = event.parse_invoice()
        print(f"New invoice: {invoice.number}")

    handler.on_payment_created(on_payment_created)
    handler.on_invoice_created(on_invoice_created)

    # Serve it with any WSGI server; wsgiref here for the example.
    with make_server("", 8080, handler) as httpd:
        print("Serving webhook on http://localhost:8080/webhook")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
