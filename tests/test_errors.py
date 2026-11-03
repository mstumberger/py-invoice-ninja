"""Tests for error types, ported from errors_test.go."""

import unittest

from invoice_ninja import APIError, is_api_error, parse_api_error


class TestAPIError(unittest.TestCase):
    def test_error_string(self):
        cases = [
            ("with message", APIError(status_code=400, message="bad request"),
             "Invoice Ninja API error (status 400): bad request"),
            ("without message", APIError(status_code=500),
             "Invoice Ninja API error (status 500)"),
        ]
        for name, err, expected in cases:
            with self.subTest(name):
                self.assertEqual(str(err), expected)

    def test_api_error_methods(self):
        cases = [
            ("IsNotFound true", APIError(status_code=404), "is_not_found", True),
            ("IsNotFound false", APIError(status_code=200), "is_not_found", False),
            ("IsUnauthorized true", APIError(status_code=401), "is_unauthorized", True),
            ("IsForbidden true", APIError(status_code=403), "is_forbidden", True),
            ("IsValidationError true", APIError(status_code=422), "is_validation_error", True),
            ("IsRateLimited true", APIError(status_code=429), "is_rate_limited", True),
            ("IsServerError true", APIError(status_code=500), "is_server_error", True),
            ("IsServerError true for 503", APIError(status_code=503), "is_server_error", True),
            ("IsServerError false for 400", APIError(status_code=400), "is_server_error", False),
        ]
        for name, err, method, expected in cases:
            with self.subTest(name):
                self.assertEqual(getattr(err, method)(), expected)

    def test_parse_api_error(self):
        cases = [
            (
                "parse JSON error",
                422,
                b'{"message":"Validation failed","errors":{"email":["Email is required"]}}',
                "Validation failed",
                {"email": ["Email is required"]},
            ),
            ("invalid JSON", 400, b"invalid json", "bad request", None),
            ("empty body 401", 401, b"", "unauthorized - check your API token", None),
            (
                "empty body 403",
                403,
                b"",
                "forbidden - you don't have permission to access this resource",
                None,
            ),
            ("empty body 404", 404, b"", "resource not found", None),
            ("empty body 429", 429, b"", "rate limit exceeded", None),
            ("empty body 500", 500, b"", "server error", None),
        ]
        for name, status_code, body, expected_message, expected_errors in cases:
            with self.subTest(name):
                err = parse_api_error(status_code, body)
                self.assertEqual(err.status_code, status_code)
                self.assertEqual(err.message, expected_message)
                if expected_errors is not None:
                    for key, value in expected_errors.items():
                        self.assertEqual(err.errors[key], value)

    def test_is_api_error(self):
        api_err = APIError(status_code=400)

        result = is_api_error(api_err)
        self.assertIs(result, api_err)

        self.assertIsNone(is_api_error(ValueError("nope")))
        self.assertIsNone(is_api_error(None))


if __name__ == "__main__":
    unittest.main()
