"""Clients service for the Invoice Ninja API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from ._options import CommonListOptions
from .errors import InvoiceNinjaError
from .models import (
    BulkAction,
    ClientPortalSwitchResponse,
    INClient,
    ListResponse,
    StatementRequest,
    parse_list_response,
    parse_single_response,
)

if TYPE_CHECKING:
    from .client import Client

__all__ = [
    "ClientsService",
    "ClientListOptions",
    "StatementRequest",
    "ClientPortalSwitchRequest",
    "ClientPortalSwitchResponse",
]


@dataclass
class ClientListOptions(CommonListOptions):
    """Optional parameters for listing clients."""

    #: Number of results per page (default 20).
    per_page: int = 0
    #: Page number.
    page: int = 0
    #: Search across multiple fields.
    filter: str = ""
    #: Filter by balance, e.g. ``"gt:1000"``, ``"lt:500"``.
    balance: str = ""
    #: Filter by status (comma-separated: active, archived, deleted).
    status: str = ""
    #: Filter by creation date.
    created_at: str = ""
    #: Filter by update date.
    updated_at: str = ""
    #: Filter by deleted status.
    is_deleted: Optional[bool] = None
    #: Sort order, e.g. ``"name|desc"``, ``"balance|asc"``.
    sort: str = ""
    #: Related entities to include (contacts, documents, activities).
    include: str = ""


@dataclass
class ClientPortalSwitchRequest:
    """A request to switch to the client portal.

    ``contact_id`` is the ID of the contact to generate the portal link for.
    If empty, the primary contact is used.
    """

    contact_id: str = ""


class ClientsService:
    """Handles client-related API operations."""

    def __init__(self, client: "Client") -> None:
        self._client = client

    def list(self, opts: Optional[ClientListOptions] = None) -> ListResponse[INClient]:
        """Retrieve a list of clients."""
        payload = self._client._do_request(
            "GET", "/api/v1/clients", opts.to_query() if opts is not None else None, None, None
        )
        return parse_list_response(payload, INClient)

    def get(self, client_id: str) -> INClient:
        """Retrieve a single client by ID."""
        payload = self._client._do_request("GET", f"/api/v1/clients/{client_id}", None, None, None)
        return parse_single_response(payload, INClient)

    def create(self, client: INClient) -> INClient:
        """Create a new client."""
        payload = self._client._do_request("POST", "/api/v1/clients", None, client, None)
        return parse_single_response(payload, INClient)

    def update(self, client_id: str, client: INClient) -> INClient:
        """Update an existing client."""
        payload = self._client._do_request("PUT", f"/api/v1/clients/{client_id}", None, client, None)
        return parse_single_response(payload, INClient)

    def delete(self, client_id: str) -> None:
        """Delete a client by ID (soft delete)."""
        self._client._do_request("DELETE", f"/api/v1/clients/{client_id}", None, None, None)

    def purge(self, client_id: str) -> None:
        """Permanently remove a client and all their records."""
        self._client._do_request("POST", f"/api/v1/clients/{client_id}/purge", None, None, None)

    def archive(self, client_id: str) -> INClient:
        """Archive a client."""
        return self._bulk_action("archive", client_id)

    def restore(self, client_id: str) -> INClient:
        """Restore an archived client."""
        return self._bulk_action("restore", client_id)

    def merge(self, primary_id: str, mergeable_id: str) -> INClient:
        """Merge two clients."""
        payload = self._client._do_request(
            "POST", f"/api/v1/clients/{primary_id}/{mergeable_id}/merge", None, None, None
        )
        return parse_single_response(payload, INClient)

    def bulk(self, action: str, ids: List[str]) -> List[INClient]:
        """Perform a bulk action on multiple clients."""
        request = BulkAction(action=action, ids=ids)
        payload = self._client._do_request("POST", "/api/v1/clients/bulk", None, request, None)
        return parse_list_response(payload, INClient).data

    def get_blank(self) -> INClient:
        """Retrieve a blank client object with default values."""
        payload = self._client._do_request("GET", "/api/v1/clients/create", None, None, None)
        return parse_single_response(payload, INClient)

    def get_statement(self, request: StatementRequest) -> bytes:
        """Not implemented; always raises. Use ``client.request`` with custom
        handling for the PDF statement response."""
        raise NotImplementedError("not implemented - use client.Request with custom handling")

    def switch_to_client_portal(self, client_id: str, contact_id: str = "") -> ClientPortalSwitchResponse:
        """Generate a magic link URL for client portal access.

        The link allows the client to access their portal without password
        authentication. This method fetches the client to get the contact_key,
        then constructs the portal URL using the pattern
        ``{base_url}/client/key_login/{contact_key}``. The *contact_id*
        parameter is optional; if empty, the primary contact is used.
        """
        try:
            client = self.get(client_id)
        except InvoiceNinjaError as err:
            raise InvoiceNinjaError(f"failed to get client: {err}") from err

        if not client.contacts:
            raise ValueError("client has no contacts")

        # Find the appropriate contact.
        contact = None
        if contact_id:
            for candidate in client.contacts:
                if candidate.id == contact_id:
                    contact = candidate
                    break
            if contact is None:
                raise ValueError(f"contact with ID {contact_id} not found")
        else:
            # Use the primary contact, or the first contact if none is primary.
            for candidate in client.contacts:
                if candidate.is_primary:
                    contact = candidate
                    break
            if contact is None:
                contact = client.contacts[0]

        if not contact.contact_key:
            raise ValueError("contact has no contact_key - portal access may be disabled")

        portal_url = f"{self._client.base_url}/client/key_login/{contact.contact_key}"
        return ClientPortalSwitchResponse(url=portal_url)

    def get_client_portal_url(self, client_id: str) -> ClientPortalSwitchResponse:
        """Generate a client portal access URL for a contact.

        A convenience wrapper around :meth:`switch_to_client_portal`.
        """
        return self.switch_to_client_portal(client_id, "")

    def _bulk_action(self, action: str, client_id: str) -> INClient:
        clients = self.bulk(action, [client_id])
        if not clients:
            raise RuntimeError("no client returned from bulk action")
        return clients[0]
