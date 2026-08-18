"""Хранение TLS reminder-state в существующей таблице ops.settings."""

import json
import threading
from datetime import datetime, timezone
from typing import Any

from app.infrastructure.database.psycopg_connection import connect_postgres
from app.monitoring.tls.models import TLSReminderState


class PostgresTLSReminderRepository:
    """Использует универсальное JSONB-хранилище ``ops.settings``."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        sslmode: str = "prefer",
        connect_timeout_sec: int = 5,
    ) -> None:
        self._conninfo = (
            f"host={host} port={port} dbname={database} user={user} "
            f"password={password} sslmode={sslmode} connect_timeout={connect_timeout_sec}"
        )
        self._lock = threading.Lock()

    def _connect(self):
        return connect_postgres(self._conninfo)

    def get_state(self, host: str) -> TLSReminderState | None:
        """Читает состояние по стабильному service-state ключу."""

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT value FROM ops.settings WHERE key = %s",
                    (_state_key(host),),
                )
                row = cur.fetchone()
        if row is None:
            return None
        value = row[0]
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, dict):
            raise ValueError("TLS reminder state must be a JSON object")
        return TLSReminderState(
            certificate_not_after=_parse_utc_datetime(value.get("certificate_not_after")),
            reminder_sent_at=_parse_utc_datetime(value.get("reminder_sent_at")),
        )

    def save_state(self, host: str, state: TLSReminderState) -> None:
        """Сохраняет состояние через idempotent upsert."""

        value = {
            "certificate_not_after": _format_utc_datetime(state.certificate_not_after),
            "reminder_sent_at": _format_utc_datetime(state.reminder_sent_at),
        }
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ops.settings(key, value, updated_at)
                    VALUES (%s, %s::jsonb, NOW())
                    ON CONFLICT (key) DO UPDATE
                    SET value = EXCLUDED.value, updated_at = NOW()
                    """,
                    (_state_key(host), json.dumps(value)),
                )
            conn.commit()


def _state_key(host: str) -> str:
    return f"tls_reminder:{host.strip().lower()}"


def _parse_utc_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("TLS reminder datetime is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("TLS reminder datetime must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _format_utc_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("TLS reminder datetime must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
