"""Credits service for the Invoice Ninja API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from ._options import CommonListOptions
from .models import BulkAction, Credit, ListResponse, parse_list_response, parse_single_response

if TYPE_CHECKING:
    from .client import Client

__all__ = ["CreditsService", "CreditListOptions"]


@dataclass
class CreditListOptions(CommonListOptions):
    """Optional parameters for listing credits."""

    per_page: int = 0
    page: int = 0
    filter: str = ""
    client_id: str = ""
    status: str = ""
    created_at: str = ""
    updated_at: str = ""
    is_deleted: Optional[bool] = None
    sort: str = ""
    include: str = ""


class CreditsService:
    """Handles credit-related API operations."""

    def __init__(self, client: "Client") -> None:
        self._client = client

    def list(self, opts: Optional[CreditListOptions] = None) -> ListResponse[Credit]:
        """Retrieve a list of credits."""
        payload = self._client._do_request(
            "GET", "/api/v1/credits", opts.to_query() if opts is not None else None, None, None
        )
        return parse_list_response(payload, Credit)

    def get(self, credit_id: str) -> Credit:
        """Retrieve a single credit by ID."""
        payload = self._client._do_request("GET", f"/api/v1/credits/{credit_id}", None, None, None)
        return parse_single_response(payload, Credit)

    def create(self, credit: Credit) -> Credit:
        """Create a new credit."""
        payload = self._client._do_request("POST", "/api/v1/credits", None, credit, None)
        return parse_single_response(payload, Credit)

    def update(self, credit_id: str, credit: Credit) -> Credit:
        """Update an existing credit."""
        payload = self._client._do_request("PUT", f"/api/v1/credits/{credit_id}", None, credit, None)
        return parse_single_response(payload, Credit)

    def delete(self, credit_id: str) -> None:
        """Delete a credit by ID."""
        self._client._do_request("DELETE", f"/api/v1/credits/{credit_id}", None, None, None)

    def bulk(self, action: str, ids: List[str]) -> List[Credit]:
        """Perform a bulk action on multiple credits."""
        request = BulkAction(action=action, ids=ids)
        payload = self._client._do_request("POST", "/api/v1/credits/bulk", None, request, None)
        return parse_list_response(payload, Credit).data

    def archive(self, credit_id: str) -> Credit:
        """Archive a credit."""
        return self._bulk_action("archive", credit_id)

    def restore(self, credit_id: str) -> Credit:
        """Restore an archived credit."""
        return self._bulk_action("restore", credit_id)

    def mark_sent(self, credit_id: str) -> Credit:
        """Mark a credit as sent."""
        return self._bulk_action("mark_sent", credit_id)

    def email(self, credit_id: str) -> Credit:
        """Send a credit via email."""
        return self._bulk_action("email", credit_id)

    def get_blank(self) -> Credit:
        """Retrieve a blank credit object with default values."""
        payload = self._client._do_request("GET", "/api/v1/credits/create", None, None, None)
        return parse_single_response(payload, Credit)

    def _bulk_action(self, action: str, credit_id: str) -> Credit:
        credits = self.bulk(action, [credit_id])
        if not credits:
            raise RuntimeError("no credit returned from bulk action")
        return credits[0]
