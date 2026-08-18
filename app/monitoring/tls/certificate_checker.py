"""Получение реально выдаваемого HTTPS-сертификата."""

import socket
import ssl
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from app.monitoring.tls.models import TLSCertificateInfo


class TLSCertificateCheckError(RuntimeError):
    """Контролируемая ошибка DNS, TCP, TLS или разбора сертификата."""


class TLSCertificateChecker:
    """Проверяет сертификат endpoint через системное доверенное хранилище."""

    def __init__(
        self,
        *,
        context_factory: Callable[[], ssl.SSLContext] = ssl.create_default_context,
        connection_factory: Callable[..., Any] = socket.create_connection,
    ) -> None:
        self._context_factory = context_factory
        self._connection_factory = connection_factory

    def check(self, *, host: str, port: int, timeout_sec: int) -> TLSCertificateInfo:
        """Возвращает срок действия сертификата в UTC."""

        try:
            context = self._context_factory()
            with self._connection_factory((host, port), timeout=timeout_sec) as raw_socket:
                with context.wrap_socket(raw_socket, server_hostname=host) as tls_socket:
                    certificate = tls_socket.getpeercert()
            not_after_raw = certificate.get("notAfter")
            if not isinstance(not_after_raw, str) or not not_after_raw.strip():
                raise ValueError("certificate has no notAfter")
            not_after_epoch = ssl.cert_time_to_seconds(not_after_raw)
            not_after = datetime.fromtimestamp(not_after_epoch, tz=timezone.utc)
        except (OSError, ssl.SSLError, TypeError, ValueError) as exc:
            raise TLSCertificateCheckError(exc.__class__.__name__) from None

        return TLSCertificateInfo(host=host, port=port, not_after=not_after)
