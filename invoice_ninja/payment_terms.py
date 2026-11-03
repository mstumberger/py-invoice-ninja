"""Payment terms service for the Invoice Ninja API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from ._options import CommonListOptions
from .models import BulkAction, ListResponse, PaymentTerm, parse_list_response, parse_single_response

if TYPE_CHECKING:
    from .client import Client

__all__ = ["PaymentTermsService", "PaymentTermListOptions"]


@dataclass
class PaymentTermListOptions(CommonListOptions):
    """Optional parameters for listing payment terms."""

    per_page: int = 0
    page: int = 0
    include: str = ""


class PaymentTermsService:
    """Handles payment terms-related API operations."""

    def __init__(self, client: "Client") -> None:
        self._client = client

    def list(self, opts: Optional[PaymentTermListOptions] = None) -> ListResponse[PaymentTerm]:
        """Retrieve a list of payment terms."""
        payload = self._client._do_request(
            "GET", "/api/v1/payment_terms", opts.to_query() if opts is not None else None, None, None
        )
        return parse_list_response(payload, PaymentTerm)

    def get(self, term_id: str) -> PaymentTerm:
        """Retrieve a single payment term by ID."""
        payload = self._client._do_request("GET", f"/api/v1/payment_terms/{term_id}", None, None, None)
        return parse_single_response(payload, PaymentTerm)

    def create(self, term: PaymentTerm) -> PaymentTerm:
        """Create a new payment term."""
        payload = self._client._do_request("POST", "/api/v1/payment_terms", None, term, None)
        return parse_single_response(payload, PaymentTerm)

    def update(self, term_id: str, term: PaymentTerm) -> PaymentTerm:
        """Update an existing payment term."""
        payload = self._client._do_request("PUT", f"/api/v1/payment_terms/{term_id}", None, term, None)
        return parse_single_response(payload, PaymentTerm)

    def delete(self, term_id: str) -> None:
        """Delete a payment term by ID."""
        self._client._do_request("DELETE", f"/api/v1/payment_terms/{term_id}", None, None, None)

    def bulk(self, action: str, ids: List[str]) -> List[PaymentTerm]:
        """Perform a bulk action on multiple payment terms."""
        request = BulkAction(action=action, ids=ids)
        payload = self._client._do_request("POST", "/api/v1/payment_terms/bulk", None, request, None)
        return parse_list_response(payload, PaymentTerm).data

    def archive(self, term_id: str) -> PaymentTerm:
        """Archive a payment term."""
        terms = self.bulk("archive", [term_id])
        if not terms:
            raise RuntimeError("no payment term returned from bulk action")
        return terms[0]

    def restore(self, term_id: str) -> PaymentTerm:
        """Restore an archived payment term."""
        terms = self.bulk("restore", [term_id])
        if not terms:
            raise RuntimeError("no payment term returned from bulk action")
        return terms[0]

    def get_blank(self) -> PaymentTerm:
        """Retrieve a blank payment term object with default values."""
        payload = self._client._do_request("GET", "/api/v1/payment_terms/create", None, None, None)
        return parse_single_response(payload, PaymentTerm)
