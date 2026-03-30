import asyncio
import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from app.helpdesk.models.ticket import Ticket, TicketStatus
from app.helpdesk.repositories.types import TicketActionResult


class SqliteTicketRepository:
    """SQLite-backed repository with minimal stage-4 ticket model."""

    def __init__(self, db_path: str) -> None:
        self._db_path = Path(db_path)
        self._lock = asyncio.Lock()
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            await asyncio.to_thread(self._init_schema_sync)
            self._initialized = True

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema_sync(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS helpdesk_tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id TEXT NOT NULL UNIQUE,
                    requester_user_id INTEGER NOT NULL,
                    requester_name TEXT,
                    category TEXT NOT NULL,
                    text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    assignee_user_id INTEGER,
                    assignee_name TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    requester_phone TEXT,
                    requester_department TEXT
                )
                """
            )
            self._ensure_column(conn, "helpdesk_tickets", "updated_at", "TEXT")
            self._ensure_column(conn, "helpdesk_tickets", "requester_name", "TEXT")
            self._ensure_column(conn, "helpdesk_tickets", "requester_phone", "TEXT")
            self._ensure_column(conn, "helpdesk_tickets", "requester_department", "TEXT")
            self._ensure_column(conn, "helpdesk_tickets", "assignee_name", "TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_helpdesk_tickets_user ON helpdesk_tickets(requester_user_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_helpdesk_tickets_status ON helpdesk_tickets(status)"
            )
            conn.commit()

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        columns = {row[1] for row in rows}
        if column in columns:
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _row_to_ticket(row: sqlite3.Row) -> Ticket:
        created_at_raw = row["created_at"]
        updated_at_raw = row["updated_at"] or created_at_raw
        created_at = datetime.fromisoformat(created_at_raw)
        updated_at = datetime.fromisoformat(updated_at_raw)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)

        status_raw = row["status"]
        try:
            status = TicketStatus(status_raw)
        except ValueError:
            status = TicketStatus.NEW

        return Ticket(
            id=row["ticket_id"],
            user_id=row["requester_user_id"],
            category=row["category"],
            text=row["text"],
            status=status,
            assigned_to=row["assignee_user_id"],
            created_at=created_at,
            updated_at=updated_at,
            requester_name=row["requester_name"],
            assignee_name=row["assignee_name"],
            requester_phone=row["requester_phone"],
            requester_department=row["requester_department"],
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
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                """
                INSERT INTO helpdesk_tickets (
                    ticket_id, requester_user_id, requester_name, category, text,
                    status, assignee_user_id, assignee_name,
                    created_at, updated_at, requester_phone, requester_department
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?)
                """,
                (
                    "PENDING",
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
            row_id = int(cur.lastrowid)
            ticket_id = f"T-{row_id:05d}"
            conn.execute(
                "UPDATE helpdesk_tickets SET ticket_id = ? WHERE id = ?",
                (ticket_id, row_id),
            )
            row = conn.execute(
                "SELECT * FROM helpdesk_tickets WHERE id = ?",
                (row_id,),
            ).fetchone()
            conn.commit()

        if row is None:
            raise RuntimeError("Could not create ticket")
        return self._row_to_ticket(row)

    async def get_by_ticket_id(self, ticket_id: str) -> Ticket | None:
        await self._ensure_initialized()
        return await asyncio.to_thread(self._get_by_ticket_id_sync, ticket_id)

    def _get_by_ticket_id_sync(self, ticket_id: str) -> Ticket | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM helpdesk_tickets WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_ticket(row)

    async def list_by_user(self, user_id: int, limit: int = 10) -> list[Ticket]:
        await self._ensure_initialized()
        return await asyncio.to_thread(self._list_by_user_sync, user_id, limit)

    def _list_by_user_sync(self, user_id: int, limit: int) -> list[Ticket]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM helpdesk_tickets
                WHERE requester_user_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [self._row_to_ticket(row) for row in rows]

    async def list_open(self, limit: int = 50) -> list[Ticket]:
        await self._ensure_initialized()
        return await asyncio.to_thread(self._list_open_sync, limit)

    def _list_open_sync(self, limit: int) -> list[Ticket]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM helpdesk_tickets
                WHERE status != ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (TicketStatus.CLOSED.value, limit),
            ).fetchall()
        return [self._row_to_ticket(row) for row in rows]

    async def update_status(self, ticket_id: str, status: str) -> TicketActionResult:
        await self._ensure_initialized()
        return await asyncio.to_thread(self._update_status_sync, ticket_id, status)

    def _update_status_sync(self, ticket_id: str, status: str) -> TicketActionResult:
        try:
            normalized = TicketStatus(status)
        except ValueError:
            return TicketActionResult(ok=False, reason="invalid_status")

        now = datetime.now(tz=timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM helpdesk_tickets WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchone()
            if row is None:
                conn.commit()
                return TicketActionResult(ok=False, reason="not_found")

            conn.execute(
                "UPDATE helpdesk_tickets SET status = ?, updated_at = ? WHERE ticket_id = ?",
                (normalized.value, now, ticket_id),
            )
            updated = conn.execute(
                "SELECT * FROM helpdesk_tickets WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchone()
            conn.commit()

        if updated is None:
            return TicketActionResult(ok=False, reason="not_found")
        return TicketActionResult(ok=True, reason="status_updated", ticket=self._row_to_ticket(updated))

    async def assign(
        self,
        ticket_id: str,
        specialist_id: int,
        specialist_name: str,
    ) -> TicketActionResult:
        await self._ensure_initialized()
        return await asyncio.to_thread(
            self._assign_sync,
            ticket_id,
            specialist_id,
            specialist_name,
        )

    def _assign_sync(
        self,
        ticket_id: str,
        specialist_id: int,
        specialist_name: str,
    ) -> TicketActionResult:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM helpdesk_tickets WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchone()
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

            conn.execute(
                """
                UPDATE helpdesk_tickets
                SET assignee_user_id = ?, assignee_name = ?, status = ?, updated_at = ?
                WHERE ticket_id = ?
                """,
                (
                    specialist_id,
                    specialist_name,
                    TicketStatus.IN_PROGRESS.value,
                    now,
                    ticket_id,
                ),
            )
            updated = conn.execute(
                "SELECT * FROM helpdesk_tickets WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchone()
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
        return await asyncio.to_thread(
            self._release_sync,
            ticket_id,
            actor_user_id,
            set(admin_ids),
        )

    def _release_sync(
        self,
        ticket_id: str,
        actor_user_id: int,
        admin_ids: set[int],
    ) -> TicketActionResult:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM helpdesk_tickets WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchone()
            if row is None:
                conn.commit()
                return TicketActionResult(ok=False, reason="not_found")

            ticket = self._row_to_ticket(row)
            if ticket.assigned_to is None:
                conn.commit()
                return TicketActionResult(ok=False, reason="not_assigned", ticket=ticket)

            is_admin = actor_user_id in admin_ids
            if ticket.assigned_to != actor_user_id and not is_admin:
                conn.commit()
                return TicketActionResult(ok=False, reason="forbidden", ticket=ticket)

            conn.execute(
                """
                UPDATE helpdesk_tickets
                SET assignee_user_id = NULL, assignee_name = NULL, status = ?, updated_at = ?
                WHERE ticket_id = ?
                """,
                (TicketStatus.NEW.value, now, ticket_id),
            )
            updated = conn.execute(
                "SELECT * FROM helpdesk_tickets WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchone()
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
            self._close_sync,
            ticket_id,
            actor_user_id,
            actor_name,
            set(admin_ids),
        )

    def _close_sync(
        self,
        ticket_id: str,
        actor_user_id: int,
        actor_name: str,
        admin_ids: set[int],
    ) -> TicketActionResult:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM helpdesk_tickets WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchone()
            if row is None:
                conn.commit()
                return TicketActionResult(ok=False, reason="not_found")

            ticket = self._row_to_ticket(row)
            if ticket.status == TicketStatus.CLOSED:
                conn.commit()
                return TicketActionResult(ok=False, reason="already_closed", ticket=ticket)

            is_admin = actor_user_id in admin_ids
            if ticket.assigned_to and ticket.assigned_to != actor_user_id and not is_admin:
                conn.commit()
                return TicketActionResult(ok=False, reason="forbidden", ticket=ticket)

            assigned_to = ticket.assigned_to or actor_user_id
            assignee_name = ticket.assignee_name or actor_name
            conn.execute(
                """
                UPDATE helpdesk_tickets
                SET assignee_user_id = ?, assignee_name = ?, status = ?, updated_at = ?
                WHERE ticket_id = ?
                """,
                (assigned_to, assignee_name, TicketStatus.CLOSED.value, now, ticket_id),
            )
            updated = conn.execute(
                "SELECT * FROM helpdesk_tickets WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchone()
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
            self._request_clarification_sync,
            ticket_id,
            actor_user_id,
            actor_name,
            set(admin_ids),
        )

    def _request_clarification_sync(
        self,
        ticket_id: str,
        actor_user_id: int,
        actor_name: str,
        admin_ids: set[int],
    ) -> TicketActionResult:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM helpdesk_tickets WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchone()
            if row is None:
                conn.commit()
                return TicketActionResult(ok=False, reason="not_found")

            ticket = self._row_to_ticket(row)
            if ticket.status == TicketStatus.CLOSED:
                conn.commit()
                return TicketActionResult(ok=False, reason="already_closed", ticket=ticket)

            is_admin = actor_user_id in admin_ids
            if ticket.assigned_to and ticket.assigned_to != actor_user_id and not is_admin:
                conn.commit()
                return TicketActionResult(ok=False, reason="forbidden", ticket=ticket)

            assigned_to = ticket.assigned_to or actor_user_id
            assignee_name = ticket.assignee_name or actor_name
            conn.execute(
                """
                UPDATE helpdesk_tickets
                SET assignee_user_id = ?, assignee_name = ?, status = ?, updated_at = ?
                WHERE ticket_id = ?
                """,
                (
                    assigned_to,
                    assignee_name,
                    TicketStatus.WAITING_USER.value,
                    now,
                    ticket_id,
                ),
            )
            updated = conn.execute(
                "SELECT * FROM helpdesk_tickets WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchone()
            conn.commit()

        if updated is None:
            return TicketActionResult(ok=False, reason="not_found")
        return TicketActionResult(ok=True, reason="waiting_user", ticket=self._row_to_ticket(updated))
