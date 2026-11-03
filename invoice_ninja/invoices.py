"""Invoices service for the Invoice Ninja API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from ._options import CommonListOptions
from .models import BulkAction, Invoice, ListResponse, parse_list_response, parse_single_response

if TYPE_CHECKING:
    from .client import Client

__all__ = ["InvoicesService", "InvoiceListOptions"]


@dataclass
class InvoiceListOptions(CommonListOptions):
    """Optional parameters for listing invoices."""

    #: Number of results per page (default 20).
    per_page: int = 0
    #: Page number.
    page: int = 0
    #: Search across multiple fields.
    filter: str = ""
    #: Filter by client.
    client_id: str = ""
    #: Filter by status (comma-separated: active, archived, deleted).
    status: str = ""
    #: Filter by creation date.
    created_at: str = ""
    #: Filter by update date.
    updated_at: str = ""
    #: Filter by deleted status.
    is_deleted: Optional[bool] = None
    #: Sort order, e.g. ``"id|desc"``, ``"number|asc"``.
    sort: str = ""
    #: Related entities to include.
    include: str = ""


class InvoicesService:
    """Handles invoice-related API operations."""

    def __init__(self, client: "Client") -> None:
        self._client = client

    def list(self, opts: Optional[InvoiceListOptions] = None) -> ListResponse[Invoice]:
        """Retrieve a list of invoices."""
        payload = self._client._do_request(
            "GET", "/api/v1/invoices", opts.to_query() if opts is not None else None, None, None
        )
        return parse_list_response(payload, Invoice)

    def get(self, invoice_id: str) -> Invoice:
        """Retrieve a single invoice by ID."""
        payload = self._client._do_request("GET", f"/api/v1/invoices/{invoice_id}", None, None, None)
        return parse_single_response(payload, Invoice)

    def create(self, invoice: Invoice) -> Invoice:
        """Create a new invoice."""
        payload = self._client._do_request("POST", "/api/v1/invoices", None, invoice, None)
        return parse_single_response(payload, Invoice)

    def update(self, invoice_id: str, invoice: Invoice) -> Invoice:
        """Update an existing invoice."""
        payload = self._client._do_request("PUT", f"/api/v1/invoices/{invoice_id}", None, invoice, None)
        return parse_single_response(payload, Invoice)

    def delete(self, invoice_id: str) -> None:
        """Delete an invoice by ID."""
        self._client._do_request("DELETE", f"/api/v1/invoices/{invoice_id}", None, None, None)

    def archive(self, invoice_id: str) -> Invoice:
        """Archive an invoice."""
        return self._bulk_action("archive", invoice_id)

    def restore(self, invoice_id: str) -> Invoice:
        """Restore an archived invoice."""
        return self._bulk_action("restore", invoice_id)

    def mark_paid(self, invoice_id: str) -> Invoice:
        """Mark an invoice as paid."""
        return self._bulk_action("mark_paid", invoice_id)

    def mark_sent(self, invoice_id: str) -> Invoice:
        """Mark an invoice as sent."""
        return self._bulk_action("mark_sent", invoice_id)

    def email(self, invoice_id: str) -> Invoice:
        """Send an invoice via email."""
        return self._bulk_action("email", invoice_id)

    def bulk(self, action: str, ids: List[str]) -> List[Invoice]:
        """Perform a bulk action on multiple invoices."""
        request = BulkAction(action=action, ids=ids)
        payload = self._client._do_request("POST", "/api/v1/invoices/bulk", None, request, None)
        return parse_list_response(payload, Invoice).data

    def get_blank(self) -> Invoice:
        """Retrieve a blank invoice object with default values."""
        payload = self._client._do_request("GET", "/api/v1/invoices/create", None, None, None)
        return parse_single_response(payload, Invoice)

    def download(self, invitation_key: str) -> bytes:
        """Download an invoice PDF by invitation key and return the raw PDF
        bytes. Delegates to DownloadsService.download_invoice_pdf."""
        return self._client.downloads.download_invoice_pdf(invitation_key)

    def _bulk_action(self, action: str, invoice_id: str) -> Invoice:
        invoices = self.bulk(action, [invoice_id])
        if not invoices:
            raise RuntimeError("no invoice returned from bulk action")
        return invoices[0]
