"""PostgreSQL-хранилище audit/events."""

import json
import threading
from typing import Any

from app.infrastructure.database.psycopg_connection import connect_postgres
from app.observability.models import AuditRecord, NetworkToolRunRecord, TicketEventRecord


class PostgresObservabilityRepository:
    """Пишет observability-записи в helpdesk.*, ops.* и network.*."""

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

    def _resolve_ticket_pk(self, cur, ticket_key: str) -> int | None:
        cur.execute(
            "SELECT id FROM helpdesk.tickets WHERE ticket_key = %s",
            (ticket_key,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return int(row[0])

    def record_ticket_event(self, record: TicketEventRecord) -> None:
        """Пишет бизнес-событие заявки."""

        payload = _safe_json(record.metadata)
        if record.actor_role:
            payload.setdefault("actor_role", record.actor_role)
        if record.source:
            payload.setdefault("source", record.source)
        if record.related_message_id:
            payload.setdefault("related_message_id", record.related_message_id)

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                ticket_pk = self._resolve_ticket_pk(cur, record.ticket_id)
                if ticket_pk is None:
                    raise LookupError(f"Ticket not found in helpdesk.tickets: {record.ticket_id}")
                cur.execute(
                    """
                    INSERT INTO helpdesk.ticket_events(
                        ticket_id, event_type, actor_user_id, actor_name,
                        old_status_code, new_status_code, actor_role, source,
                        related_message_id, payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        ticket_pk,
                        record.event_type,
                        record.actor_user_id,
                        record.actor_name,
                        record.old_status,
                        record.new_status,
                        record.actor_role,
                        record.source,
                        record.related_message_id,
                        json.dumps(payload, ensure_ascii=False),
                    ),
                )
            conn.commit()

    def record_audit(self, record: AuditRecord) -> None:
        """Пишет audit record."""

        entity_type = record.resource_type
        entity_id = record.resource_id
        metadata = _safe_json(record.metadata)
        metadata.setdefault("result", record.result)
        if record.reason:
            metadata.setdefault("reason", record.reason)
        if record.actor_role:
            metadata.setdefault("actor_role", record.actor_role)

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ops.audit_log(
                        actor_user_id, action, entity_type, entity_id, payload,
                        actor_role, resource_type, resource_id, result, reason, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        record.actor_user_id,
                        record.action,
                        entity_type,
                        entity_id,
                        json.dumps(metadata, ensure_ascii=False),
                        record.actor_role,
                        record.resource_type,
                        record.resource_id,
                        record.result,
                        record.reason,
                        json.dumps(metadata, ensure_ascii=False),
                    ),
                )
            conn.commit()

    def record_network_tool_run(self, record: NetworkToolRunRecord) -> None:
        """Пишет результат сетевого инструмента."""

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO network.tool_runs(
                        actor_user_id, actor_name, tool, target, normalized_target,
                        policy_decision, success, duration_ms, output_excerpt,
                        error_text, status, started_at, finished_at, output_truncated,
                        feature_enabled, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        record.actor_user_id,
                        record.actor_name,
                        record.tool,
                        record.target,
                        record.normalized_target,
                        record.policy_decision,
                        record.status == "success",
                        record.duration_ms,
                        record.output_excerpt,
                        record.error_text,
                        record.status,
                        record.started_at,
                        record.finished_at,
                        record.output_truncated,
                        record.feature_enabled,
                        json.dumps(_safe_json(record.metadata), ensure_ascii=False),
                    ),
                )
            conn.commit()


def _safe_json(value: dict[str, Any] | None) -> dict[str, Any]:
    """Возвращает JSON-safe dict без приватных URL/token полей."""

    if not value:
        return {}
    blocked = {"token", "url", "media_url", "upload_url", "password", "api_key"}
    result: dict[str, Any] = {}
    for key, item in value.items():
        key_text = str(key)
        if key_text.lower() in blocked:
            continue
        if isinstance(item, dict):
            result[key_text] = _safe_json(item)
        elif isinstance(item, (str, int, float, bool)) or item is None:
            result[key_text] = item
        else:
            result[key_text] = str(item)
    return result
