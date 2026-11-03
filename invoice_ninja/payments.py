"""Payments service for the Invoice Ninja API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from ._options import CommonListOptions
from .models import BulkAction, ListResponse, Payment, PaymentRequest, RefundRequest, parse_list_response, parse_single_response

if TYPE_CHECKING:
    from .client import Client

__all__ = ["PaymentsService", "PaymentListOptions"]


@dataclass
class PaymentListOptions(CommonListOptions):
    """Optional parameters for listing payments."""

    #: Number of results per page (default 20).
    per_page: int = 0
    #: Page number.
    page: int = 0
    #: Search across amount, date and custom values.
    filter: str = ""
    #: Search by payment number.
    number: str = ""
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
    #: Filter by vendor.
    vendor_id: str = ""
    #: Sort order, e.g. ``"amount|desc"``, ``"number|asc"``.
    sort: str = ""
    #: Related entities to include.
    include: str = ""


class PaymentsService:
    """Handles payment-related API operations."""

    def __init__(self, client: "Client") -> None:
        self._client = client

    def list(self, opts: Optional[PaymentListOptions] = None) -> ListResponse[Payment]:
        """Retrieve a list of payments."""
        payload = self._client._do_request(
            "GET", "/api/v1/payments", opts.to_query() if opts is not None else None, None, None
        )
        return parse_list_response(payload, Payment)

    def get(self, payment_id: str) -> Payment:
        """Retrieve a single payment by ID."""
        payload = self._client._do_request("GET", f"/api/v1/payments/{payment_id}", None, None, None)
        return parse_single_response(payload, Payment)

    def create(self, payment: PaymentRequest) -> Payment:
        """Create a new payment."""
        payload = self._client._do_request("POST", "/api/v1/payments", None, payment, None)
        return parse_single_response(payload, Payment)

    def create_with_email_receipt(self, payment: PaymentRequest, send_email: bool) -> Payment:
        """Create a new payment and optionally send an email receipt."""
        query = {"email_receipt": ["true" if send_email else "false"]}
        payload = self._client._do_request("POST", "/api/v1/payments", query, payment, None)
        return parse_single_response(payload, Payment)

    def update(self, payment_id: str, payment: PaymentRequest) -> Payment:
        """Update an existing payment."""
        payload = self._client._do_request("PUT", f"/api/v1/payments/{payment_id}", None, payment, None)
        return parse_single_response(payload, Payment)

    def delete(self, payment_id: str) -> None:
        """Delete a payment by ID."""
        self._client._do_request("DELETE", f"/api/v1/payments/{payment_id}", None, None, None)

    def refund(self, refund: RefundRequest) -> Payment:
        """Create a refund for a payment."""
        payload = self._client._do_request("POST", "/api/v1/payments/refund", None, refund, None)
        return parse_single_response(payload, Payment)

    def archive(self, payment_id: str) -> Payment:
        """Archive a payment."""
        return self._bulk_action("archive", payment_id)

    def restore(self, payment_id: str) -> Payment:
        """Restore an archived payment."""
        return self._bulk_action("restore", payment_id)

    def bulk(self, action: str, ids: List[str]) -> List[Payment]:
        """Perform a bulk action on multiple payments."""
        request = BulkAction(action=action, ids=ids)
        payload = self._client._do_request("POST", "/api/v1/payments/bulk", None, request, None)
        return parse_list_response(payload, Payment).data

    def get_blank(self) -> Payment:
        """Retrieve a blank payment object with default values."""
        payload = self._client._do_request("GET", "/api/v1/payments/create", None, None, None)
        return parse_single_response(payload, Payment)

    def _bulk_action(self, action: str, payment_id: str) -> Payment:
        payments = self.bulk(action, [payment_id])
        if not payments:
            raise RuntimeError("no payment returned from bulk action")
        return payments[0]
