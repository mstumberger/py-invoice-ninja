"""Tests for downloads and uploads, ported from files_test.go."""

import io
import json
import os
import tempfile
import unittest

from invoice_ninja import Client, is_api_error

from .support import TestServer


def _json(payload):
    return json.dumps(payload).encode("utf-8")


class TestDownloadsService(unittest.TestCase):
    def test_download_invoice_pdf(self):
        expected_pdf = b"%PDF-1.4 fake pdf content"

        def callback(request):
            self.assertEqual(request.method, "GET")
            self.assertTrue(request.path.startswith("/api/v1/invoice/"))
            self.assertTrue(request.path.endswith("/download"))
            self.assertEqual(request.path, "/api/v1/invoice/inv-key-123/download")
            self.assertEqual(request.header("X-API-TOKEN"), "test-token")
            self.assertEqual(request.header("Accept"), "application/pdf")
            return 200, {"Content-Type": "application/pdf"}, expected_pdf

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        pdf = client.downloads.download_invoice_pdf("inv-key-123")
        self.assertEqual(pdf, expected_pdf)

    def test_download_paths(self):
        cases = [
            (("download_invoice_delivery_note", "inv123"), "/api/v1/invoices/inv123/delivery_note"),
            (("download_credit_pdf", "cr-key"), "/api/v1/credit/cr-key/download"),
            (("download_quote_pdf", "q-key"), "/api/v1/quote/q-key/download"),
        ]
        for (method, arg), expected_path in cases:
            with self.subTest(method=method):
                seen = {}
                server = TestServer(lambda request: (seen.setdefault("path", request.path), (200, {"Content-Type": "application/pdf"}, b"%PDF-1.4"))[1])
                self.addCleanup(server.close)

                client = Client("test-token", base_url=server.url)
                getattr(client.downloads, method)(arg)
                self.assertEqual(seen["path"], expected_path)

    def test_download_error(self):
        server = TestServer(lambda request: (404, {}, _json({"message": "Invoice not found"})))
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        with self.assertRaises(Exception) as ctx:
            client.downloads.download_invoice_pdf("invalid-key")

        api_err = is_api_error(ctx.exception)
        self.assertIsNotNone(api_err)
        self.assertTrue(api_err.is_not_found())


class TestUploadsService(unittest.TestCase):
    def test_upload_from_reader(self):
        def callback(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.path, "/api/v1/invoices/inv123/upload")

            content_type = request.header("Content-Type")
            self.assertTrue(content_type.startswith("multipart/form-data"))

            # Check _method field.
            self.assertIn(b'name="_method"', request.body)
            self.assertIn(b"PUT", request.body)

            # Check the file was uploaded under documents[] with its filename.
            self.assertIn(b'name="documents[]"', request.body)
            self.assertIn(b'filename="test.pdf"', request.body)
            self.assertIn(b"test content", request.body)
            return 200, {}, b""

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        client.uploads.upload_document_from_reader("invoices", "inv123", "test.pdf", io.BytesIO(b"test content"))

    def test_upload_error(self):
        server = TestServer(lambda request: (422, {}, _json({"message": "Invalid file type"})))
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        with self.assertRaises(Exception) as ctx:
            client.uploads.upload_document_from_reader(
                "invoices", "inv123", "test.exe", io.BytesIO(b"test content")
            )

        api_err = is_api_error(ctx.exception)
        self.assertIsNotNone(api_err)
        self.assertTrue(api_err.is_validation_error())

    def test_upload_paths(self):
        cases = [
            (("upload_invoice_document", "inv1"), "/api/v1/invoices/inv1/upload"),
            (("upload_payment_document", "pay1"), "/api/v1/payments/pay1/upload"),
            (("upload_client_document", "cli1"), "/api/v1/clients/cli1/upload"),
            (("upload_credit_document", "cr1"), "/api/v1/credits/cr1/upload"),
            (("upload_document", "expenses", "exp1"), "/api/v1/expenses/exp1/upload"),
        ]
        for (method, *args), expected_path in cases:
            with self.subTest(method=method):
                seen = {}
                server = TestServer(
                    lambda request: (seen.setdefault("path", request.path), (200, {}, b""))[1]
                )
                self.addCleanup(server.close)

                client = Client("test-token", base_url=server.url)
                if method == "upload_document":
                    client.uploads.upload_document(args[0], args[1], self._temp_file())
                else:
                    getattr(client.uploads, method)(args[0], self._temp_file())
                self.assertEqual(seen["path"], expected_path)

    def test_upload_file_from_filesystem(self):
        def callback(request):
            self.assertIn(b'filename="upload.txt"', request.body)
            self.assertIn(b"file body", request.body)
            return 200, {}, b""

        server = TestServer(callback)
        self.addCleanup(server.close)

        client = Client("test-token", base_url=server.url)
        client.uploads.upload_invoice_document("inv1", self._temp_file())

    @staticmethod
    def _temp_file() -> str:
        return TestUploadsService._named_file("upload.txt")

    @staticmethod
    def _named_file(name: str) -> str:
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, name)
        with open(path, "w") as handle:
            handle.write("file body")
        return path


if __name__ == "__main__":
    unittest.main()
