"""PostgreSQL-хранилище hotel-specific контекста заявки."""

import json
import threading
from datetime import datetime, timezone
from typing import Any

from psycopg.rows import dict_row

from app.helpdesk.models.room_ticket_history import RoomTicketHistoryItem
from app.helpdesk.models.room_ticket_context import RoomTicketContext
from app.infrastructure.database.psycopg_connection import connect_postgres


_STATUS_CODE_TO_DISPLAY = {
    "new": "новое",
    "in_progress": "в работе",
    "waiting_user": "ожидает пользователя",
    "closed": "закрыто",
}


class PostgresRoomTicketContextRepository:
    """Сохраняет и читает снимок номера/категории из helpdesk.ticket_context."""

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
        return connect_postgres(self._conninfo, row_factory=dict_row)

    def save(self, context: RoomTicketContext) -> RoomTicketContext:
        """Создает или обновляет контекст заявки по ticket_key."""

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO helpdesk.ticket_context(
                        ticket_key, hotel_id, location_id, issue_category_id,
                        room_number_snapshot, location_display_snapshot,
                        category_snapshot, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (ticket_key) DO UPDATE SET
                        hotel_id = EXCLUDED.hotel_id,
                        location_id = EXCLUDED.location_id,
                        issue_category_id = EXCLUDED.issue_category_id,
                        room_number_snapshot = EXCLUDED.room_number_snapshot,
                        location_display_snapshot = EXCLUDED.location_display_snapshot,
                        category_snapshot = EXCLUDED.category_snapshot,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                    RETURNING *
                    """,
                    (
                        context.ticket_key,
                        context.hotel_id,
                        context.location_id,
                        context.issue_category_id,
                        context.room_number_snapshot,
                        context.location_display_snapshot,
                        context.category_snapshot,
                        json.dumps(context.metadata or {}, ensure_ascii=False),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("Could not save room ticket context")
        return _context_from_row(row)

    def get_by_ticket_key(self, ticket_key: str) -> RoomTicketContext | None:
        """Возвращает контекст заявки или None."""

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM helpdesk.ticket_context
                    WHERE ticket_key = %s
                    LIMIT 1
                    """,
                    (ticket_key,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return _context_from_row(row)

    def list_recent_tickets_for_location(
        self,
        hotel_id: int,
        location_id: int,
        *,
        exclude_ticket_key: str | None = None,
        limit: int = 10,
    ) -> list[RoomTicketHistoryItem]:
        """Читает историю заявок по объекту из ticket_context и normalized mirror."""

        where_exclude = ""
        params: list[Any] = [hotel_id, location_id]
        if exclude_ticket_key:
            where_exclude = "AND tc.ticket_key <> %s"
            params.append(str(exclude_ticket_key))
        params.append(int(limit))

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                        tc.ticket_key,
                        tc.hotel_id,
                        tc.location_id,
                        tc.category_snapshot,
                        t.status_code,
                        COALESCE(t.created_at, tc.created_at) AS created_at,
                        t.closed_at
                    FROM helpdesk.ticket_context tc
                    JOIN helpdesk.tickets t ON t.ticket_key = tc.ticket_key
                    WHERE tc.hotel_id = %s
                      AND tc.location_id = %s
                      AND tc.location_id IS NOT NULL
                      {where_exclude}
                    ORDER BY COALESCE(t.created_at, tc.created_at) DESC
                    LIMIT %s
                    """,
                    tuple(params),
                )
                rows = cur.fetchall() or []
        return [_history_item_from_row(row) for row in rows]


def _context_from_row(row: dict[str, Any]) -> RoomTicketContext:
    metadata = row.get("metadata") or {}
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    return RoomTicketContext(
        ticket_key=str(row["ticket_key"]),
        hotel_id=int(row["hotel_id"]),
        location_id=int(row["location_id"]) if row["location_id"] is not None else None,
        issue_category_id=(
            int(row["issue_category_id"])
            if row["issue_category_id"] is not None
            else None
        ),
        room_number_snapshot=(
            str(row["room_number_snapshot"])
            if row["room_number_snapshot"] is not None
            else None
        ),
        location_display_snapshot=(
            str(row["location_display_snapshot"])
            if row["location_display_snapshot"] is not None
            else None
        ),
        category_snapshot=(
            str(row["category_snapshot"])
            if row["category_snapshot"] is not None
            else None
        ),
        metadata=dict(metadata),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _history_item_from_row(row: dict[str, Any]) -> RoomTicketHistoryItem:
    return RoomTicketHistoryItem(
        ticket_key=str(row["ticket_key"]),
        hotel_id=int(row["hotel_id"]),
        location_id=int(row["location_id"]),
        category_snapshot=(
            str(row["category_snapshot"])
            if row.get("category_snapshot") is not None
            else None
        ),
        status=_STATUS_CODE_TO_DISPLAY.get(
            str(row["status_code"]) if row.get("status_code") is not None else "",
            None,
        ),
        created_at=_as_aware_datetime(row["created_at"]),
        closed_at=(
            _as_aware_datetime(row["closed_at"])
            if row.get("closed_at") is not None
            else None
        ),
    )


def _as_aware_datetime(raw: datetime | str) -> datetime:
    if isinstance(raw, datetime):
        value = raw
    else:
        value = datetime.fromisoformat(str(raw))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value
