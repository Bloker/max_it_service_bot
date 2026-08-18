"""SQLAlchemy-репозиторий заявок поверх нормализованной схемы helpdesk."""

import asyncio
from collections.abc import Iterable
from datetime import datetime, timezone
from hashlib import md5
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.engine import create_sqlalchemy_engine, dispose_sqlalchemy_engine
from app.db.session import create_session_factory, session_scope
from app.helpdesk.models.ticket import Ticket, TicketStatus
from app.helpdesk.repositories.types import TicketActionResult
from config.config import TicketStorageConfig


_STATUS_TO_CODE = {
    TicketStatus.NEW: "new",
    TicketStatus.IN_PROGRESS: "in_progress",
    TicketStatus.WAITING_USER: "waiting_user",
    TicketStatus.CLOSED: "closed",
}

_CODE_TO_STATUS = {
    "new": TicketStatus.NEW,
    "in_progress": TicketStatus.IN_PROGRESS,
    "waiting_user": TicketStatus.WAITING_USER,
    "closed": TicketStatus.CLOSED,
}


class PostgresNormalizedTicketRepository:
    """Репозиторий source-of-truth для `helpdesk.tickets`."""

    def __init__(
        self,
        config: TicketStorageConfig,
        *,
        engine: Engine | None = None,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self._owns_engine = engine is None and session_factory is None
        self._engine = engine or (
            create_sqlalchemy_engine(config)
            if session_factory is None
            else None
        )
        self._session_factory = session_factory or create_session_factory(self._engine)
        self._lock = asyncio.Lock()

    async def create_ticket(
        self,
        requester_user_id: int,
        requester_name: str,
        category: str,
        text: str,
        requester_phone: str | None = None,
        requester_department: str | None = None,
    ) -> Ticket:
        """Создает заявку сразу с финальным `ticket_key` без PENDING."""

        async with self._lock:
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
        body: str,
        requester_phone: str | None,
        requester_department: str | None,
    ) -> Ticket:
        now = datetime.now(tz=timezone.utc)
        with session_scope(self._session_factory) as session:
            row_id = int(
                session.execute(
                    text("SELECT nextval(pg_get_serial_sequence('helpdesk.tickets', 'id'))")
                ).scalar_one()
            )
            ticket_key = f"T-{row_id:05d}"
            category_code = self._resolve_category_code(session, category)
            session.execute(
                text(
                    """
                    INSERT INTO helpdesk.tickets(
                        id, ticket_key, requester_user_id, requester_name,
                        requester_phone, requester_department, category_code,
                        status_code, assignee_user_id, assignee_name,
                        description, created_at, updated_at, closed_at
                    )
                    VALUES (
                        :id, :ticket_key, :requester_user_id, :requester_name,
                        :requester_phone, :requester_department, :category_code,
                        :status_code, NULL, NULL,
                        :description, :created_at, :updated_at, NULL
                    )
                    """
                ),
                {
                    "id": row_id,
                    "ticket_key": ticket_key,
                    "requester_user_id": requester_user_id,
                    "requester_name": requester_name,
                    "requester_phone": requester_phone,
                    "requester_department": requester_department,
                    "category_code": category_code,
                    "status_code": _STATUS_TO_CODE[TicketStatus.NEW],
                    "description": body,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            row = self._select_ticket_row(session, ticket_key, for_update=False)
        if row is None:
            raise RuntimeError("Could not create normalized ticket")
        return self._row_to_ticket(row)

    async def get_by_ticket_id(self, ticket_id: str) -> Ticket | None:
        return await asyncio.to_thread(self._get_by_ticket_id_sync, ticket_id)

    def _get_by_ticket_id_sync(self, ticket_id: str) -> Ticket | None:
        with session_scope(self._session_factory) as session:
            row = self._select_ticket_row(session, ticket_id, for_update=False)
        return self._row_to_ticket(row) if row else None

    async def list_by_user(self, user_id: int, limit: int = 10) -> list[Ticket]:
        return await asyncio.to_thread(self._list_by_user_sync, user_id, limit)

    def _list_by_user_sync(self, user_id: int, limit: int) -> list[Ticket]:
        with session_scope(self._session_factory) as session:
            rows = (
                session.execute(
                    text(
                        f"""
                        {self._select_ticket_base_sql()}
                        WHERE t.requester_user_id = :user_id
                        ORDER BY t.updated_at DESC
                        LIMIT :limit
                        """
                    ),
                    {"user_id": user_id, "limit": limit},
                )
                .mappings()
                .all()
            )
        return [self._row_to_ticket(row) for row in rows]

    async def list_open(self, limit: int = 50) -> list[Ticket]:
        return await asyncio.to_thread(self._list_open_sync, limit)

    def _list_open_sync(self, limit: int) -> list[Ticket]:
        with session_scope(self._session_factory) as session:
            rows = (
                session.execute(
                    text(
                        f"""
                        {self._select_ticket_base_sql()}
                        WHERE t.status_code != :closed_status
                        ORDER BY t.updated_at DESC
                        LIMIT :limit
                        """
                    ),
                    {"closed_status": _STATUS_TO_CODE[TicketStatus.CLOSED], "limit": limit},
                )
                .mappings()
                .all()
            )
        return [self._row_to_ticket(row) for row in rows]

    async def update_status(self, ticket_id: str, status: str) -> TicketActionResult:
        return await asyncio.to_thread(self._update_status_sync, ticket_id, status)

    def _update_status_sync(self, ticket_id: str, status: str) -> TicketActionResult:
        try:
            normalized = TicketStatus(status)
        except ValueError:
            return TicketActionResult(ok=False, reason="invalid_status")
        now = datetime.now(tz=timezone.utc)
        with session_scope(self._session_factory) as session:
            row = self._select_ticket_row(session, ticket_id, for_update=True)
            if row is None:
                return TicketActionResult(ok=False, reason="not_found")
            session.execute(
                text(
                    """
                    UPDATE helpdesk.tickets
                    SET status_code = :status_code,
                        updated_at = :updated_at,
                        closed_at = :closed_at
                    WHERE ticket_key = :ticket_key
                    """
                ),
                {
                    "status_code": _STATUS_TO_CODE[normalized],
                    "updated_at": now,
                    "closed_at": now if normalized == TicketStatus.CLOSED else None,
                    "ticket_key": ticket_id,
                },
            )
            updated = self._select_ticket_row(session, ticket_id, for_update=False)
        if updated is None:
            return TicketActionResult(ok=False, reason="not_found")
        return TicketActionResult(ok=True, reason="status_updated", ticket=self._row_to_ticket(updated))

    async def reopen(self, ticket_id: str) -> TicketActionResult:
        """Атомарно повторно открывает нормализованную заявку."""

        return await asyncio.to_thread(self._reopen_sync, ticket_id)

    def _reopen_sync(self, ticket_id: str) -> TicketActionResult:
        now = datetime.now(tz=timezone.utc)
        with session_scope(self._session_factory) as session:
            row = self._select_ticket_row(session, ticket_id, for_update=True)
            if row is None:
                return TicketActionResult(ok=False, reason="not_found")
            ticket = self._row_to_ticket(row)
            if ticket.status != TicketStatus.CLOSED:
                return TicketActionResult(ok=False, reason="already_open", ticket=ticket)
            status = TicketStatus.IN_PROGRESS if ticket.assigned_to else TicketStatus.NEW
            session.execute(
                text(
                    """
                    UPDATE helpdesk.tickets
                    SET status_code = :status_code,
                        updated_at = :updated_at,
                        closed_at = NULL
                    WHERE ticket_key = :ticket_key
                    """
                ),
                {
                    "status_code": _STATUS_TO_CODE[status],
                    "updated_at": now,
                    "ticket_key": ticket_id,
                },
            )
            updated = self._select_ticket_row(session, ticket_id, for_update=False)
        return TicketActionResult(ok=True, reason="reopened", ticket=self._row_to_ticket(updated))

    async def assign(
        self,
        ticket_id: str,
        specialist_id: int,
        specialist_name: str,
    ) -> TicketActionResult:
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
        now = datetime.now(tz=timezone.utc)
        with session_scope(self._session_factory) as session:
            row = self._select_ticket_row(session, ticket_id, for_update=True)
            if row is None:
                return TicketActionResult(ok=False, reason="not_found")
            ticket = self._row_to_ticket(row)
            if ticket.status == TicketStatus.CLOSED:
                return TicketActionResult(ok=False, reason="already_closed", ticket=ticket)
            if ticket.assigned_to and ticket.assigned_to != specialist_id:
                return TicketActionResult(ok=False, reason="already_assigned", ticket=ticket)
            session.execute(
                text(
                    """
                    UPDATE helpdesk.tickets
                    SET assignee_user_id = :assignee_user_id,
                        assignee_name = :assignee_name,
                        status_code = :status_code,
                        updated_at = :updated_at,
                        closed_at = NULL
                    WHERE ticket_key = :ticket_key
                    """
                ),
                {
                    "assignee_user_id": specialist_id,
                    "assignee_name": specialist_name,
                    "status_code": _STATUS_TO_CODE[TicketStatus.IN_PROGRESS],
                    "updated_at": now,
                    "ticket_key": ticket_id,
                },
            )
            updated = self._select_ticket_row(session, ticket_id, for_update=False)
        if updated is None:
            return TicketActionResult(ok=False, reason="not_found")
        return TicketActionResult(ok=True, reason="assigned", ticket=self._row_to_ticket(updated))

    async def release(
        self,
        ticket_id: str,
        actor_user_id: int,
        admin_ids: Iterable[int],
    ) -> TicketActionResult:
        return await asyncio.to_thread(self._release_sync, ticket_id, actor_user_id, set(admin_ids))

    def _release_sync(
        self,
        ticket_id: str,
        actor_user_id: int,
        admin_ids: set[int],
    ) -> TicketActionResult:
        now = datetime.now(tz=timezone.utc)
        with session_scope(self._session_factory) as session:
            row = self._select_ticket_row(session, ticket_id, for_update=True)
            if row is None:
                return TicketActionResult(ok=False, reason="not_found")
            ticket = self._row_to_ticket(row)
            if ticket.assigned_to is None:
                return TicketActionResult(ok=False, reason="not_assigned", ticket=ticket)
            if ticket.assigned_to != actor_user_id and actor_user_id not in admin_ids:
                return TicketActionResult(ok=False, reason="forbidden", ticket=ticket)
            session.execute(
                text(
                    """
                    UPDATE helpdesk.tickets
                    SET assignee_user_id = NULL,
                        assignee_name = NULL,
                        status_code = :status_code,
                        updated_at = :updated_at,
                        closed_at = NULL
                    WHERE ticket_key = :ticket_key
                    """
                ),
                {
                    "status_code": _STATUS_TO_CODE[TicketStatus.NEW],
                    "updated_at": now,
                    "ticket_key": ticket_id,
                },
            )
            updated = self._select_ticket_row(session, ticket_id, for_update=False)
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
        now = datetime.now(tz=timezone.utc)
        with session_scope(self._session_factory) as session:
            row = self._select_ticket_row(session, ticket_id, for_update=True)
            if row is None:
                return TicketActionResult(ok=False, reason="not_found")
            ticket = self._row_to_ticket(row)
            if ticket.status == TicketStatus.CLOSED:
                return TicketActionResult(ok=False, reason="already_closed", ticket=ticket)
            if ticket.assigned_to and ticket.assigned_to != actor_user_id and actor_user_id not in admin_ids:
                return TicketActionResult(ok=False, reason="forbidden", ticket=ticket)
            assigned_to = ticket.assigned_to or actor_user_id
            assignee_name = ticket.assignee_name or actor_name
            session.execute(
                text(
                    """
                    UPDATE helpdesk.tickets
                    SET assignee_user_id = :assignee_user_id,
                        assignee_name = :assignee_name,
                        status_code = :status_code,
                        updated_at = :updated_at,
                        closed_at = :closed_at
                    WHERE ticket_key = :ticket_key
                    """
                ),
                {
                    "assignee_user_id": assigned_to,
                    "assignee_name": assignee_name,
                    "status_code": _STATUS_TO_CODE[TicketStatus.CLOSED],
                    "updated_at": now,
                    "closed_at": now,
                    "ticket_key": ticket_id,
                },
            )
            updated = self._select_ticket_row(session, ticket_id, for_update=False)
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
        now = datetime.now(tz=timezone.utc)
        with session_scope(self._session_factory) as session:
            row = self._select_ticket_row(session, ticket_id, for_update=True)
            if row is None:
                return TicketActionResult(ok=False, reason="not_found")
            ticket = self._row_to_ticket(row)
            if ticket.status == TicketStatus.CLOSED:
                return TicketActionResult(ok=False, reason="already_closed", ticket=ticket)
            if ticket.assigned_to and ticket.assigned_to != actor_user_id and actor_user_id not in admin_ids:
                return TicketActionResult(ok=False, reason="forbidden", ticket=ticket)
            assigned_to = ticket.assigned_to or actor_user_id
            assignee_name = ticket.assignee_name or actor_name
            session.execute(
                text(
                    """
                    UPDATE helpdesk.tickets
                    SET assignee_user_id = :assignee_user_id,
                        assignee_name = :assignee_name,
                        status_code = :status_code,
                        updated_at = :updated_at,
                        closed_at = NULL
                    WHERE ticket_key = :ticket_key
                    """
                ),
                {
                    "assignee_user_id": assigned_to,
                    "assignee_name": assignee_name,
                    "status_code": _STATUS_TO_CODE[TicketStatus.WAITING_USER],
                    "updated_at": now,
                    "ticket_key": ticket_id,
                },
            )
            updated = self._select_ticket_row(session, ticket_id, for_update=False)
        if updated is None:
            return TicketActionResult(ok=False, reason="not_found")
        return TicketActionResult(ok=True, reason="waiting_user", ticket=self._row_to_ticket(updated))

    def close_engine(self) -> None:
        """Закрывает engine, если репозиторий сам его создал."""

        if self._owns_engine and self._engine is not None:
            dispose_sqlalchemy_engine(self._engine)

    @staticmethod
    def _select_ticket_base_sql() -> str:
        return """
            SELECT
                t.ticket_key,
                t.requester_user_id,
                t.requester_name,
                t.requester_phone,
                t.requester_department,
                t.category_code,
                COALESCE(c.display_name, t.category_code) AS category_display_name,
                t.status_code,
                t.assignee_user_id,
                t.assignee_name,
                t.description,
                t.created_at,
                t.updated_at,
                t.closed_at
            FROM helpdesk.tickets t
            LEFT JOIN helpdesk.categories c ON c.code = t.category_code
        """

    def _select_ticket_row(
        self,
        session: Session,
        ticket_key: str,
        *,
        for_update: bool,
    ) -> dict[str, Any] | None:
        lock_clause = "FOR UPDATE" if for_update else ""
        row = (
            session.execute(
                text(
                    f"""
                    {self._select_ticket_base_sql()}
                    WHERE t.ticket_key = :ticket_key
                    {lock_clause}
                    """
                ),
                {"ticket_key": ticket_key},
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def _resolve_category_code(self, session: Session, category: str) -> str:
        display_name = (category or "Прочее").strip() or "Прочее"
        row = (
            session.execute(
                text("SELECT code FROM helpdesk.categories WHERE display_name = :display_name"),
                {"display_name": display_name},
            )
            .mappings()
            .first()
        )
        if row is not None:
            return str(row["code"])

        category_code = f"cat_{md5(display_name.encode('utf-8')).hexdigest()[:12]}"
        session.execute(
            text(
                """
                INSERT INTO helpdesk.categories(code, display_name, is_active)
                VALUES (:code, :display_name, TRUE)
                ON CONFLICT (display_name) DO UPDATE
                SET is_active = TRUE
                RETURNING code
                """
            ),
            {"code": category_code, "display_name": display_name},
        )
        row = (
            session.execute(
                text("SELECT code FROM helpdesk.categories WHERE display_name = :display_name"),
                {"display_name": display_name},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise RuntimeError(f"Could not resolve category: {display_name}")
        return str(row["code"])

    @staticmethod
    def _as_aware_datetime(raw: datetime | str) -> datetime:
        if isinstance(raw, datetime):
            value = raw
        else:
            value = datetime.fromisoformat(str(raw))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value

    @classmethod
    def _row_to_ticket(cls, row: dict[str, Any]) -> Ticket:
        status = _CODE_TO_STATUS.get(str(row["status_code"]), TicketStatus.NEW)
        return Ticket(
            id=str(row["ticket_key"]),
            user_id=int(row["requester_user_id"]),
            requester_name=row.get("requester_name"),
            requester_phone=row.get("requester_phone"),
            requester_department=row.get("requester_department"),
            category=str(row.get("category_display_name") or row.get("category_code") or "Прочее"),
            text=str(row["description"]),
            status=status,
            assigned_to=(
                int(row["assignee_user_id"])
                if row.get("assignee_user_id") is not None
                else None
            ),
            assignee_name=row.get("assignee_name"),
            created_at=cls._as_aware_datetime(row["created_at"]),
            updated_at=cls._as_aware_datetime(row.get("updated_at") or row["created_at"]),
        )


__all__ = ["PostgresNormalizedTicketRepository"]
