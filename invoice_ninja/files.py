"""File download and upload operations for the Invoice Ninja API."""

from __future__ import annotations

import os
import secrets
from typing import TYPE_CHECKING, BinaryIO, Tuple

from .client import _APIRequest

if TYPE_CHECKING:
    from .client import Client

__all__ = ["DownloadsService", "UploadsService"]

_JSON_MEDIA_TYPE = "application/json"


class DownloadsService:
    """Handles file download operations."""

    def __init__(self, client: "Client") -> None:
        self._client = client

    def download_invoice_pdf(self, invitation_key: str) -> bytes:
        """Download an invoice PDF by invitation key."""
        return self._download_file(f"/api/v1/invoice/{invitation_key}/download")

    def download_invoice_delivery_note(self, invoice_id: str) -> bytes:
        """Download an invoice delivery note PDF."""
        return self._download_file(f"/api/v1/invoices/{invoice_id}/delivery_note")

    def download_credit_pdf(self, invitation_key: str) -> bytes:
        """Download a credit PDF by invitation key."""
        return self._download_file(f"/api/v1/credit/{invitation_key}/download")

    def download_quote_pdf(self, invitation_key: str) -> bytes:
        """Download a quote PDF by invitation key."""
        return self._download_file(f"/api/v1/quote/{invitation_key}/download")

    def _download_file(self, path: str) -> bytes:
        """Perform a file download request."""
        return self._client._execute(
            _APIRequest(
                method="GET",
                url=self._client.base_url + path,
                content_type="",
                accept="application/pdf",
            )
        )


class UploadsService:
    """Handles file upload operations."""

    def __init__(self, client: "Client") -> None:
        self._client = client

    def upload_document(self, entity_type: str, entity_id: str, file_path: str) -> None:
        """Upload a document to an entity."""
        return self._upload_file(f"/api/v1/{entity_type}/{entity_id}/upload", file_path)

    def upload_invoice_document(self, invoice_id: str, file_path: str) -> None:
        """Upload a document to an invoice."""
        return self._upload_file(f"/api/v1/invoices/{invoice_id}/upload", file_path)

    def upload_payment_document(self, payment_id: str, file_path: str) -> None:
        """Upload a document to a payment."""
        return self._upload_file(f"/api/v1/payments/{payment_id}/upload", file_path)

    def upload_client_document(self, client_id: str, file_path: str) -> None:
        """Upload a document to a client."""
        return self._upload_file(f"/api/v1/clients/{client_id}/upload", file_path)

    def upload_credit_document(self, credit_id: str, file_path: str) -> None:
        """Upload a document to a credit."""
        return self._upload_file(f"/api/v1/credits/{credit_id}/upload", file_path)

    def upload_document_from_reader(
        self, entity_type: str, entity_id: str, filename: str, reader: BinaryIO
    ) -> None:
        """Upload a document from a binary file object."""
        return self._upload_from_reader(f"/api/v1/{entity_type}/{entity_id}/upload", filename, reader)

    def _upload_file(self, path: str, file_path: str) -> None:
        """Upload a file from the filesystem."""
        try:
            with open(file_path, "rb") as file:
                return self._upload_from_reader(path, os.path.basename(file_path), file)
        except OSError as err:
            raise OSError(f"failed to open file: {err}") from err

    def _upload_from_reader(self, path: str, filename: str, reader: BinaryIO) -> None:
        """Upload a file from a binary file object."""
        body, content_type = _build_multipart_body(filename, reader)

        self._client._execute(
            _APIRequest(
                method="POST",
                url=self._client.base_url + path,
                body=body,
                content_type=content_type,
                accept=_JSON_MEDIA_TYPE,
            )
        )


def _build_multipart_body(filename: str, reader: BinaryIO) -> Tuple[bytes, str]:
    """Build a multipart body with a ``_method=PUT`` override field and the
    file under the ``documents[]`` field, mirroring Go's mime/multipart."""
    boundary = secrets.token_hex(30)

    parts: list[bytes] = []

    # _method field for the PUT override.
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="_method"\r\n'
            f"\r\n"
            f"PUT\r\n"
        ).encode("utf-8")
    )

    # The file part.
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="documents[]"; filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n"
            f"\r\n"
        ).encode("utf-8")
    )
    parts.append(reader.read())
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))

    body = b"".join(parts)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type
