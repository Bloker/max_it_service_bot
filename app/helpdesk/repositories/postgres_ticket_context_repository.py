"""PostgreSQL-хранилище комментариев и metadata вложений заявок."""

import json
import threading
from typing import Any

from app.helpdesk.repositories.ticket_context_repository import (
    TicketAttachmentRecord,
    TicketCommentRecord,
)


class PostgresTicketContextRepository:
    """Сохраняет persistent-контекст карточки заявки в helpdesk.*."""

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
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL ticket context repository requires psycopg."
            ) from exc
        return psycopg.connect(self._conninfo, row_factory=dict_row)

    def _resolve_ticket_pk(self, cur, ticket_key: str) -> int | None:
        cur.execute(
            "SELECT id FROM helpdesk.tickets WHERE ticket_key = %s",
            (ticket_key,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return int(row["id"])

    def save_comment(
        self,
        *,
        ticket_id: str,
        direction: str,
        body: str,
        author_user_id: int | None = None,
        author_name: str | None = None,
        author_role: str | None = None,
        source_message_id: str | None = None,
        target_message_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> TicketCommentRecord:
        """Сохраняет комментарий заявки."""

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                ticket_pk = self._resolve_ticket_pk(cur, ticket_id)
                if ticket_pk is None:
                    raise LookupError(f"Ticket not found in helpdesk.tickets: {ticket_id}")
                cur.execute(
                    """
                    INSERT INTO helpdesk.ticket_comments(
                        ticket_id, author_user_id, author_name, direction, body,
                        author_role, source_message_id, target_message_id, meta
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    RETURNING *
                    """,
                    (
                        ticket_pk,
                        author_user_id,
                        author_name,
                        direction,
                        body,
                        author_role,
                        source_message_id,
                        target_message_id,
                        json.dumps(meta or {}, ensure_ascii=False),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("Could not save ticket comment")
        return self._comment_from_row(row, ticket_id=ticket_id)

    def save_attachment(
        self,
        *,
        ticket_id: str,
        comment_id: int | None = None,
        platform_attachment_type: str | None = None,
        platform_attachment_ref: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> TicketAttachmentRecord:
        """Сохраняет metadata вложения без приватных URL."""

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                ticket_pk = self._resolve_ticket_pk(cur, ticket_id)
                if ticket_pk is None:
                    raise LookupError(f"Ticket not found in helpdesk.tickets: {ticket_id}")
                cur.execute(
                    """
                    INSERT INTO helpdesk.ticket_attachments(
                        ticket_id, comment_id, platform_attachment_type,
                        platform_attachment_ref, meta
                    )
                    VALUES (%s, %s, %s, %s, %s::jsonb)
                    RETURNING *
                    """,
                    (
                        ticket_pk,
                        comment_id,
                        platform_attachment_type,
                        platform_attachment_ref,
                        json.dumps(meta or {}, ensure_ascii=False),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("Could not save ticket attachment")
        return self._attachment_from_row(row, ticket_id=ticket_id)

    def list_attachments(
        self,
        *,
        ticket_id: str,
        source: str | None = None,
        comment_id: int | None = None,
    ) -> list[TicketAttachmentRecord]:
        """Возвращает metadata вложений заявки."""

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                ticket_pk = self._resolve_ticket_pk(cur, ticket_id)
                if ticket_pk is None:
                    return []
                filters = ["ticket_id = %s"]
                params: list[Any] = [ticket_pk]
                if source is not None:
                    filters.append("meta->>'source' = %s")
                    params.append(source)
                if comment_id is not None:
                    filters.append("comment_id = %s")
                    params.append(comment_id)
                cur.execute(
                    f"""
                    SELECT *
                    FROM helpdesk.ticket_attachments
                    WHERE {" AND ".join(filters)}
                    ORDER BY id ASC
                    """,
                    tuple(params),
                )
                rows = cur.fetchall()
        return [self._attachment_from_row(row, ticket_id=ticket_id) for row in rows]

    def get_last_comment(
        self,
        *,
        ticket_id: str,
        direction: str,
        attached_to_card: bool | None = None,
    ) -> TicketCommentRecord | None:
        """Возвращает последний комментарий нужного типа."""

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                ticket_pk = self._resolve_ticket_pk(cur, ticket_id)
                if ticket_pk is None:
                    return None
                filters = ["ticket_id = %s", "direction = %s"]
                params: list[Any] = [ticket_pk, direction]
                if attached_to_card is not None:
                    filters.append("meta->>'attached_to_card' = %s")
                    params.append("true" if attached_to_card else "false")
                cur.execute(
                    f"""
                    SELECT *
                    FROM helpdesk.ticket_comments
                    WHERE {" AND ".join(filters)}
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                    """,
                    tuple(params),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return self._comment_from_row(row, ticket_id=ticket_id)

    def get_user_reply_by_group_message(
        self,
        group_message_id: str,
    ) -> TicketCommentRecord | None:
        """Ищет ответ пользователя по ID сообщения в группе."""

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT c.*, t.ticket_key
                    FROM helpdesk.ticket_comments c
                    JOIN helpdesk.tickets t ON t.id = c.ticket_id
                    WHERE c.direction = 'user_reply'
                      AND c.target_message_id = %s
                    ORDER BY c.created_at DESC, c.id DESC
                    LIMIT 1
                    """,
                    (str(group_message_id),),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return self._comment_from_row(row, ticket_id=str(row["ticket_key"]))

    def mark_user_reply_attached(self, group_message_id: str) -> TicketCommentRecord | None:
        """Помечает ответ пользователя как прикреплённый к карточке."""

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE helpdesk.ticket_comments c
                    SET meta = COALESCE(c.meta, '{}'::jsonb)
                        || '{"attached_to_card": true}'::jsonb
                    FROM helpdesk.tickets t
                    WHERE c.ticket_id = t.id
                      AND c.direction = 'user_reply'
                      AND c.target_message_id = %s
                    RETURNING c.*, t.ticket_key
                    """,
                    (str(group_message_id),),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            return None
        return self._comment_from_row(row, ticket_id=str(row["ticket_key"]))

    def _comment_from_row(self, row: dict[str, Any], *, ticket_id: str) -> TicketCommentRecord:
        return TicketCommentRecord(
            id=int(row["id"]),
            ticket_id=ticket_id,
            direction=str(row["direction"]),
            body=str(row["body"]),
            created_at=row["created_at"],
            author_user_id=(
                int(row["author_user_id"])
                if row.get("author_user_id") is not None
                else None
            ),
            author_name=row.get("author_name"),
            author_role=row.get("author_role"),
            source_message_id=row.get("source_message_id"),
            target_message_id=row.get("target_message_id"),
            meta=dict(row.get("meta") or {}),
        )

    def _attachment_from_row(
        self,
        row: dict[str, Any],
        *,
        ticket_id: str,
    ) -> TicketAttachmentRecord:
        return TicketAttachmentRecord(
            id=int(row["id"]),
            ticket_id=ticket_id,
            comment_id=int(row["comment_id"]) if row.get("comment_id") is not None else None,
            platform_attachment_type=row.get("platform_attachment_type"),
            platform_attachment_ref=row.get("platform_attachment_ref"),
            meta=dict(row.get("meta") or {}),
        )
