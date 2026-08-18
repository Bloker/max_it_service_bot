"""Модели проверки TLS-сертификата и состояния напоминания."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TLSCertificateInfo:
    """Минимальные безопасные сведения о выданном сертификате."""

    host: str
    port: int
    not_after: datetime


@dataclass(frozen=True)
class TLSReminderState:
    """Состояние дедупликации напоминания для одного сертификата."""

    certificate_not_after: datetime
    reminder_sent_at: datetime
