"""PostgreSQL-реализация репозитория заявок."""

import asyncio
from collections.abc import Iterable
from datetime import datetime, timezone

from app.infrastructure.database.psycopg_connection import connect_postgres
from app.helpdesk.models.ticket import Ticket, TicketStatus
from app.helpdesk.repositories.types import TicketActionResult


class PostgresTicketRepository:
    """PostgreSQL-репозиторий заявок для рабочего режима."""

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
        self._lock = asyncio.Lock()
        self._initialized = False

    def _connect(self):
        try:
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL backend requires psycopg. Install dependencies from requirements.txt"
            ) from exc
        return connect_postgres(self._conninfo, row_factory=dict_row)

    async def _ensure_initialized(self) -> None:
        """Лениво создает таблицу заявок и индексы."""

        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            await asyncio.to_thread(self._init_schema_sync)
            self._initialized = True

    def _init_schema_sync(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS public.helpdesk_tickets (
                        id BIGSERIAL PRIMARY KEY,
                        ticket_id TEXT NOT NULL UNIQUE,
                        requester_user_id BIGINT NOT NULL,
                        requester_name TEXT,
                        category TEXT NOT NULL,
                        text TEXT NOT NULL,
                        status TEXT NOT NULL,
                        assignee_user_id BIGINT,
                        assignee_name TEXT,
                        created_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL,
                        requester_phone TEXT,
                        requester_department TEXT
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_helpdesk_tickets_user
                    ON public.helpdesk_tickets(requester_user_id)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_helpdesk_tickets_status
                    ON public.helpdesk_tickets(status)
                    """
                )
            conn.commit()

    @staticmethod
    def _as_aware_datetime(raw: datetime | str) -> datetime:
        if isinstance(raw, datetime):
            value = raw
        else:
            value = datetime.fromisoformat(str(raw))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value

    @staticmethod
    def _row_to_ticket(row: dict) -> Ticket:
        created_at = PostgresTicketRepository._as_aware_datetime(row["created_at"])
        updated_at = PostgresTicketRepository._as_aware_datetime(
            row.get("updated_at") or row["created_at"]
        )
        try:
            status = TicketStatus(str(row["status"]))
        except ValueError:
            status = TicketStatus.NEW

        return Ticket(
            id=row["ticket_id"],
            user_id=int(row["requester_user_id"]),
            category=row["category"],
            text=row["text"],
            status=status,
            assigned_to=int(row["assignee_user_id"]) if row["assignee_user_id"] is not None else None,
            created_at=created_at,
            updated_at=updated_at,
            requester_name=row.get("requester_name"),
            assignee_name=row.get("assignee_name"),
            requester_phone=row.get("requester_phone"),
            requester_department=row.get("requester_department"),
        )

    async def create_ticket(
        self,
        requester_user_id: int,
        requester_name: str,
        category: str,
        text: str,
        requester_phone: str | None = None,
        requester_department: str | None = None,
    ) -> Ticket:
        await self._ensure_initialized()
        return await asyncio.to_thread(
            self._create_ticket_sync,
            requester_user_id,
            requester_name,
            category,
            text,
            requester_phone,
            requester_department,
        )

    def _create_ticket_sync(
        self,
        requester_user_id: int,
        requester_name: str,
        category: str,
        text: str,
        requester_phone: str | None,
        requester_department: str | None,
    ) -> Ticket:
        """Создает заявку без промежуточного PENDING ticket_id."""

        now = datetime.now(tz=timezone.utc)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT nextval(pg_get_serial_sequence('public.helpdesk_tickets', 'id')) AS id"
                )
                inserted_id = cur.fetchone()
                if inserted_id is None:
                    raise RuntimeError("Could not allocate ticket id")
                row_id = int(inserted_id["id"])
                ticket_id = f"T-{row_id:05d}"

                cur.execute(
                    """
                    INSERT INTO public.helpdesk_tickets (
                        id, ticket_id, requester_user_id, requester_name, category, text,
                        status, assignee_user_id, assignee_name,
                        created_at, updated_at, requester_phone, requester_department
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, NULL, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        row_id,
                        ticket_id,
                        requester_user_id,
                        requester_name,
                        category,
                        text,
                        TicketStatus.NEW.value,
                        now,
                        now,
                        requester_phone,
                        requester_department,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("Could not create ticket")
        return self._row_to_ticket(row)

    async def get_by_ticket_id(self, ticket_id: str) -> Ticket | None:
        await self._ensure_initialized()
        return await asyncio.to_thread(self._get_by_ticket_id_sync, ticket_id)

    def _get_by_ticket_id_sync(self, ticket_id: str) -> Ticket | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM public.helpdesk_tickets WHERE ticket_id = %s",
                    (ticket_id,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_ticket(row)

    async def list_by_user(self, user_id: int, limit: int = 10) -> list[Ticket]:
        await self._ensure_initialized()
        return await asyncio.to_thread(self._list_by_user_sync, user_id, limit)

    def _list_by_user_sync(self, user_id: int, limit: int) -> list[Ticket]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM public.helpdesk_tickets
                    WHERE requester_user_id = %s
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                    (user_id, limit),
                )
                rows = cur.fetchall()
        return [self._row_to_ticket(row) for row in rows]

    async def list_open(self, limit: int = 50) -> list[Ticket]:
        await self._ensure_initialized()
        return await asyncio.to_thread(self._list_open_sync, limit)

    def _list_open_sync(self, limit: int) -> list[Ticket]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM public.helpdesk_tickets
                    WHERE status != %s
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                    (TicketStatus.CLOSED.value, limit),
                )
                rows = cur.fetchall()
        return [self._row_to_ticket(row) for row in rows]

    async def update_status(self, ticket_id: str, status: str) -> TicketActionResult:
        await self._ensure_initialized()
        return await asyncio.to_thread(self._update_status_sync, ticket_id, status)

    def _update_status_sync(self, ticket_id: str, status: str) -> TicketActionResult:
        try:
            normalized = TicketStatus(status)
        except ValueError:
            return TicketActionResult(ok=False, reason="invalid_status")
        now = datetime.now(tz=timezone.utc)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM public.helpdesk_tickets WHERE ticket_id = %s FOR UPDATE",
                    (ticket_id,),
                )
                row = cur.fetchone()
                if row is None:
                    conn.commit()
                    return TicketActionResult(ok=False, reason="not_found")
                cur.execute(
                    """
                    UPDATE public.helpdesk_tickets
                    SET status = %s, updated_at = %s
                    WHERE ticket_id = %s
                    """,
                    (normalized.value, now, ticket_id),
                )
                cur.execute(
                    "SELECT * FROM public.helpdesk_tickets WHERE ticket_id = %s",
                    (ticket_id,),
                )
                updated = cur.fetchone()
            conn.commit()
        if updated is None:
            return TicketActionResult(ok=False, reason="not_found")
        return TicketActionResult(ok=True, reason="status_updated", ticket=self._row_to_ticket(updated))

    async def reopen(self, ticket_id: str) -> TicketActionResult:
        """Атомарно повторно открывает legacy-заявку."""

        await self._ensure_initialized()
        return await asyncio.to_thread(self._reopen_sync, ticket_id)

    def _reopen_sync(self, ticket_id: str) -> TicketActionResult:
        now = datetime.now(tz=timezone.utc)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM public.helpdesk_tickets WHERE ticket_id = %s FOR UPDATE",
                    (ticket_id,),
                )
                row = cur.fetchone()
                if row is None:
                    conn.commit()
                    return TicketActionResult(ok=False, reason="not_found")
                ticket = self._row_to_ticket(row)
                if ticket.status != TicketStatus.CLOSED:
                    conn.commit()
                    return TicketActionResult(ok=False, reason="already_open", ticket=ticket)
                status = TicketStatus.IN_PROGRESS if ticket.assigned_to else TicketStatus.NEW
                cur.execute(
                    """
                    UPDATE public.helpdesk_tickets
                    SET status = %s, updated_at = %s
                    WHERE ticket_id = %s
                    RETURNING *
                    """,
                    (status.value, now, ticket_id),
                )
                updated = cur.fetchone()
            conn.commit()
        return TicketActionResult(ok=True, reason="reopened", ticket=self._row_to_ticket(updated))

    async def assign(
        self,
        ticket_id: str,
        specialist_id: int,
        specialist_name: str,
    ) -> TicketActionResult:
        await self._ensure_initialized()
        return await asyncio.to_thread(self._assign_sync, ticket_id, specialist_id, specialist_name)

    def _assign_sync(self, ticket_id: str, specialist_id: int, specialist_name: str) -> TicketActionResult:
        now = datetime.now(tz=timezone.utc)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM public.helpdesk_tickets WHERE ticket_id = %s FOR UPDATE",
                    (ticket_id,),
                )
                row = cur.fetchone()
                if row is None:
                    conn.commit()
                    return TicketActionResult(ok=False, reason="not_found")
                ticket = self._row_to_ticket(row)
                if ticket.status == TicketStatus.CLOSED:
                    conn.commit()
                    return TicketActionResult(ok=False, reason="already_closed", ticket=ticket)
                if ticket.assigned_to and ticket.assigned_to != specialist_id:
                    conn.commit()
                    return TicketActionResult(ok=False, reason="already_assigned", ticket=ticket)
                cur.execute(
                    """
                    UPDATE public.helpdesk_tickets
                    SET assignee_user_id = %s, assignee_name = %s, status = %s, updated_at = %s
                    WHERE ticket_id = %s
                    """,
                    (specialist_id, specialist_name, TicketStatus.IN_PROGRESS.value, now, ticket_id),
                )
                cur.execute(
                    "SELECT * FROM public.helpdesk_tickets WHERE ticket_id = %s",
                    (ticket_id,),
                )
                updated = cur.fetchone()
            conn.commit()
        if updated is None:
            return TicketActionResult(ok=False, reason="not_found")
        return TicketActionResult(ok=True, reason="assigned", ticket=self._row_to_ticket(updated))

    async def release(
        self,
        ticket_id: str,
        actor_user_id: int,
        admin_ids: Iterable[int],
    ) -> TicketActionResult:
        await self._ensure_initialized()
        return await asyncio.to_thread(self._release_sync, ticket_id, actor_user_id, set(admin_ids))

    def _release_sync(self, ticket_id: str, actor_user_id: int, admin_ids: set[int]) -> TicketActionResult:
        now = datetime.now(tz=timezone.utc)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM public.helpdesk_tickets WHERE ticket_id = %s FOR UPDATE",
                    (ticket_id,),
                )
                row = cur.fetchone()
                if row is None:
                    conn.commit()
                    return TicketActionResult(ok=False, reason="not_found")
                ticket = self._row_to_ticket(row)
                if ticket.assigned_to is None:
                    conn.commit()
                    return TicketActionResult(ok=False, reason="not_assigned", ticket=ticket)
                if ticket.assigned_to != actor_user_id and actor_user_id not in admin_ids:
                    conn.commit()
                    return TicketActionResult(ok=False, reason="forbidden", ticket=ticket)
                cur.execute(
                    """
                    UPDATE public.helpdesk_tickets
                    SET assignee_user_id = NULL, assignee_name = NULL, status = %s, updated_at = %s
                    WHERE ticket_id = %s
                    """,
                    (TicketStatus.NEW.value, now, ticket_id),
                )
                cur.execute(
                    "SELECT * FROM public.helpdesk_tickets WHERE ticket_id = %s",
                    (ticket_id,),
                )
                updated = cur.fetchone()
            conn.commit()
        if updated is None:
            return TicketActionResult(ok=False, reason="not_found")
        return TicketActionResult(ok=True, reason="released", ticket=self._row_to_ticket(updated))

    async def close(
        self,
        ticket_id: str,
        actor_user_id: int,
        actor_name: str,
        admin_ids: Iterable[int],
    ) -> TicketActionResult:
        await self._ensure_initialized()
        return await asyncio.to_thread(
            self._close_sync, ticket_id, actor_user_id, actor_name, set(admin_ids)
        )

    def _close_sync(
        self,
        ticket_id: str,
        actor_user_id: int,
        actor_name: str,
        admin_ids: set[int],
    ) -> TicketActionResult:
        now = datetime.now(tz=timezone.utc)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM public.helpdesk_tickets WHERE ticket_id = %s FOR UPDATE",
                    (ticket_id,),
                )
                row = cur.fetchone()
                if row is None:
                    conn.commit()
                    return TicketActionResult(ok=False, reason="not_found")
                ticket = self._row_to_ticket(row)
                if ticket.status == TicketStatus.CLOSED:
                    conn.commit()
                    return TicketActionResult(ok=False, reason="already_closed", ticket=ticket)
                if ticket.assigned_to and ticket.assigned_to != actor_user_id and actor_user_id not in admin_ids:
                    conn.commit()
                    return TicketActionResult(ok=False, reason="forbidden", ticket=ticket)
                assigned_to = ticket.assigned_to or actor_user_id
                assignee_name = ticket.assignee_name or actor_name
                cur.execute(
                    """
                    UPDATE public.helpdesk_tickets
                    SET assignee_user_id = %s, assignee_name = %s, status = %s, updated_at = %s
                    WHERE ticket_id = %s
                    """,
                    (assigned_to, assignee_name, TicketStatus.CLOSED.value, now, ticket_id),
                )
                cur.execute(
                    "SELECT * FROM public.helpdesk_tickets WHERE ticket_id = %s",
                    (ticket_id,),
                )
                updated = cur.fetchone()
            conn.commit()
        if updated is None:
            return TicketActionResult(ok=False, reason="not_found")
        return TicketActionResult(ok=True, reason="closed", ticket=self._row_to_ticket(updated))

    async def request_clarification(
        self,
        ticket_id: str,
        actor_user_id: int,
        actor_name: str,
        admin_ids: Iterable[int],
    ) -> TicketActionResult:
        await self._ensure_initialized()
        return await asyncio.to_thread(
            self._request_clarification_sync, ticket_id, actor_user_id, actor_name, set(admin_ids)
        )

    def _request_clarification_sync(
        self,
        ticket_id: str,
        actor_user_id: int,
        actor_name: str,
        admin_ids: set[int],
    ) -> TicketActionResult:
        now = datetime.now(tz=timezone.utc)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM public.helpdesk_tickets WHERE ticket_id = %s FOR UPDATE",
                    (ticket_id,),
                )
                row = cur.fetchone()
                if row is None:
                    conn.commit()
                    return TicketActionResult(ok=False, reason="not_found")
                ticket = self._row_to_ticket(row)
                if ticket.status == TicketStatus.CLOSED:
                    conn.commit()
                    return TicketActionResult(ok=False, reason="already_closed", ticket=ticket)
                if ticket.assigned_to and ticket.assigned_to != actor_user_id and actor_user_id not in admin_ids:
                    conn.commit()
                    return TicketActionResult(ok=False, reason="forbidden", ticket=ticket)
                assigned_to = ticket.assigned_to or actor_user_id
                assignee_name = ticket.assignee_name or actor_name
                cur.execute(
                    """
                    UPDATE public.helpdesk_tickets
                    SET assignee_user_id = %s, assignee_name = %s, status = %s, updated_at = %s
                    WHERE ticket_id = %s
                    """,
                    (
                        assigned_to,
                        assignee_name,
                        TicketStatus.WAITING_USER.value,
                        now,
                        ticket_id,
                    ),
                )
                cur.execute(
                    "SELECT * FROM public.helpdesk_tickets WHERE ticket_id = %s",
                    (ticket_id,),
                )
                updated = cur.fetchone()
            conn.commit()
        if updated is None:
            return TicketActionResult(ok=False, reason="not_found")
        return TicketActionResult(ok=True, reason="waiting_user", ticket=self._row_to_ticket(updated))
