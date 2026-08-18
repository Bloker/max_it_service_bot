"""Контракт persistence для дедупликации TLS-напоминаний."""

from typing import Protocol

from app.monitoring.tls.models import TLSReminderState


class TLSReminderRepository(Protocol):
    """Читает и сохраняет reminder-state вне памяти процесса."""

    def get_state(self, host: str) -> TLSReminderState | None:
        """Возвращает последнее отправленное напоминание для домена."""

    def save_state(self, host: str, state: TLSReminderState) -> None:
        """Атомарно сохраняет состояние для домена."""
