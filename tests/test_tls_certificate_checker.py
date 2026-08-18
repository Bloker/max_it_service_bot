import socket
import ssl
import unittest
from datetime import timezone
from unittest.mock import patch

from app.monitoring.tls.certificate_checker import (
    TLSCertificateChecker,
    TLSCertificateCheckError,
)


class _ContextManager:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class _TLSSocket(_ContextManager):
    def __init__(self, certificate):
        self._certificate = certificate

    def getpeercert(self):
        return self._certificate


class _TLSContext:
    def __init__(self, certificate):
        self.check_hostname = True
        self.verify_mode = ssl.CERT_REQUIRED
        self._certificate = certificate
        self.server_hostname = None

    def wrap_socket(self, raw_socket, *, server_hostname):
        self.server_hostname = server_hostname
        return _TLSSocket(self._certificate)


class TLSCertificateCheckerTests(unittest.TestCase):
    def test_valid_certificate_is_parsed_to_aware_utc_datetime(self) -> None:
        context = _TLSContext({"notAfter": "Oct  4 12:01:06 2026 GMT"})
        connection_args = {}

        def connect(address, *, timeout):
            connection_args.update(address=address, timeout=timeout)
            return _ContextManager()

        checker = TLSCertificateChecker(
            context_factory=lambda: context,
            connection_factory=connect,
        )
        certificate = checker.check(
            host="max.myservicedomain.ru",
            port=443,
            timeout_sec=10,
        )

        self.assertEqual(certificate.not_after.tzinfo, timezone.utc)
        self.assertEqual(certificate.not_after.isoformat(), "2026-10-04T12:01:06+00:00")
        self.assertEqual(connection_args["address"], ("max.myservicedomain.ru", 443))
        self.assertEqual(connection_args["timeout"], 10)
        self.assertEqual(context.server_hostname, "max.myservicedomain.ru")
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

    def test_timeout_is_converted_to_controlled_error(self) -> None:
        def connect(address, *, timeout):
            raise socket.timeout()

        checker = TLSCertificateChecker(connection_factory=connect)

        with self.assertRaises(TLSCertificateCheckError):
            checker.check(host="example.test", port=443, timeout_sec=1)

    def test_tls_error_is_converted_to_controlled_error(self) -> None:
        context = _TLSContext({"notAfter": "invalid"})
        checker = TLSCertificateChecker(
            context_factory=lambda: context,
            connection_factory=lambda *args, **kwargs: _ContextManager(),
        )

        with patch("ssl.cert_time_to_seconds", side_effect=ValueError("invalid")):
            with self.assertRaises(TLSCertificateCheckError):
                checker.check(host="example.test", port=443, timeout_sec=1)

    def test_default_context_enables_ca_and_hostname_verification(self) -> None:
        context = ssl.create_default_context()

        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)


if __name__ == "__main__":
    unittest.main()
