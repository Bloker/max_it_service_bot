"""PostgreSQL-связь заявок с сообщениями MAX."""

import threading

from app.infrastructure.database.psycopg_connection import connect_postgres


class PostgresTicketLinkService:
    """Постоянное сопоставление заявок и сообщений в PostgreSQL."""

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
        self._initialized = False

    def _connect(self):
        try:
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL ticket link service requires psycopg. Install dependencies from requirements.txt"
            ) from exc
        return connect_postgres(self._conninfo, row_factory=dict_row)

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("CREATE SCHEMA IF NOT EXISTS integration")
                    cur.execute("CREATE SCHEMA IF NOT EXISTS helpdesk")
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS integration.message_links (
                            id BIGSERIAL PRIMARY KEY,
                            ticket_id BIGINT NOT NULL REFERENCES helpdesk.tickets(id) ON DELETE CASCADE,
                            platform TEXT NOT NULL,
                            chat_id TEXT NOT NULL,
                            message_id TEXT NOT NULL,
                            direction TEXT NOT NULL,
                            is_primary BOOLEAN NOT NULL DEFAULT FALSE,
                            linked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (platform, chat_id, message_id)
                        )
                        """
                    )
                conn.commit()
            self._initialized = True

    def _resolve_ticket_pk(self, cur, ticket_key: str) -> int | None:
        cur.execute(
            "SELECT id FROM helpdesk.tickets WHERE ticket_key = %s",
            (ticket_key,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return int(row["id"])

    def bind_group_message(
        self,
        ticket_id: str,
        group_message_id: str,
        *,
        primary: bool = False,
    ) -> None:
        self._ensure_initialized()
        normalized_mid = str(group_message_id)
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                ticket_pk = self._resolve_ticket_pk(cur, ticket_id)
                if ticket_pk is None:
                    conn.commit()
                    return

                cur.execute(
                    """
                    SELECT 1
                    FROM integration.message_links
                    WHERE ticket_id = %s AND direction = 'group' AND is_primary = TRUE
                    LIMIT 1
                    """,
                    (ticket_pk,),
                )
                has_primary = cur.fetchone() is not None
                make_primary = bool(primary or not has_primary)

                if primary:
                    cur.execute(
                        """
                        UPDATE integration.message_links
                        SET is_primary = FALSE
                        WHERE ticket_id = %s AND direction = 'group'
                        """,
                        (ticket_pk,),
                    )

                cur.execute(
                    """
                    INSERT INTO integration.message_links(
                        ticket_id, platform, chat_id, message_id, direction, is_primary
                    )
                    VALUES (%s, 'max', 'group', %s, 'group', %s)
                    ON CONFLICT (platform, chat_id, message_id) DO UPDATE
                    SET
                        ticket_id = EXCLUDED.ticket_id,
                        direction = EXCLUDED.direction,
                        is_primary = (integration.message_links.is_primary OR EXCLUDED.is_primary),
                        linked_at = NOW()
                    """,
                    (ticket_pk, normalized_mid, make_primary),
                )
            conn.commit()

    def get_group_message_id(self, ticket_id: str) -> str | None:
        self._ensure_initialized()
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                ticket_pk = self._resolve_ticket_pk(cur, ticket_id)
                if ticket_pk is None:
                    return None
                cur.execute(
                    """
                    SELECT message_id
                    FROM integration.message_links
                    WHERE ticket_id = %s AND direction = 'group'
                    ORDER BY is_primary DESC, linked_at ASC
                    LIMIT 1
                    """,
                    (ticket_pk,),
                )
                row = cur.fetchone()
        return str(row["message_id"]) if row else None

    def get_ticket_id_by_group_message(self, group_message_id: str) -> str | None:
        self._ensure_initialized()
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT t.ticket_key
                    FROM integration.message_links ml
                    JOIN helpdesk.tickets t ON t.id = ml.ticket_id
                    WHERE ml.platform = 'max'
                      AND ml.chat_id = 'group'
                      AND ml.direction = 'group'
                      AND ml.message_id = %s
                    ORDER BY ml.is_primary DESC, ml.linked_at DESC
                    LIMIT 1
                    """,
                    (str(group_message_id),),
                )
                row = cur.fetchone()
        return str(row["ticket_key"]) if row else None

    def bind_user_message(self, ticket_id: str, user_message_id: str) -> None:
        self._ensure_initialized()
        normalized_mid = str(user_message_id)
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                ticket_pk = self._resolve_ticket_pk(cur, ticket_id)
                if ticket_pk is None:
                    conn.commit()
                    return
                cur.execute(
                    """
                    INSERT INTO integration.message_links(
                        ticket_id, platform, chat_id, message_id, direction, is_primary
                    )
                    VALUES (%s, 'max', 'dialog', %s, 'user', FALSE)
                    ON CONFLICT (platform, chat_id, message_id) DO UPDATE
                    SET
                        ticket_id = EXCLUDED.ticket_id,
                        direction = EXCLUDED.direction,
                        linked_at = NOW()
                    """,
                    (ticket_pk, normalized_mid),
                )
            conn.commit()

    def get_ticket_id_by_user_message(self, user_message_id: str) -> str | None:
        self._ensure_initialized()
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT t.ticket_key
                    FROM integration.message_links ml
                    JOIN helpdesk.tickets t ON t.id = ml.ticket_id
                    WHERE ml.platform = 'max'
                      AND ml.chat_id = 'dialog'
                      AND ml.direction = 'user'
                      AND ml.message_id = %s
                    ORDER BY ml.linked_at DESC
                    LIMIT 1
                    """,
                    (str(user_message_id),),
                )
                row = cur.fetchone()
        return str(row["ticket_key"]) if row else None
