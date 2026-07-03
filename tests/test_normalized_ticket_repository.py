import unittest
from datetime import datetime, timezone

from app.helpdesk.models.ticket import TicketStatus
from app.helpdesk.repositories.postgres_normalized_ticket_repository import (
    PostgresNormalizedTicketRepository,
)
from config.config import TicketStorageConfig


class _FakeResult:
    def __init__(self, *, scalar=None, rows=None) -> None:
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one(self):
        return self._scalar

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self) -> None:
        self.calls = []
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.category_code = "cat_other"
        self.status_code = "new"
        self.assignee_user_id = None
        self.assignee_name = None
        self.ticket_key = None

    def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        self.calls.append((sql, params))
        if "nextval(pg_get_serial_sequence('helpdesk.tickets'" in sql:
            return _FakeResult(scalar=123)
        if "SELECT code FROM helpdesk.categories" in sql:
            return _FakeResult(rows=[{"code": self.category_code}])
        if "INSERT INTO helpdesk.tickets" in sql:
            self.ticket_key = params["ticket_key"]
            self.status_code = params["status_code"]
            return _FakeResult()
        if "UPDATE helpdesk.tickets" in sql:
            self.status_code = params.get("status_code", self.status_code)
            self.assignee_user_id = params.get("assignee_user_id", self.assignee_user_id)
            self.assignee_name = params.get("assignee_name", self.assignee_name)
            return _FakeResult()
        if "FROM helpdesk.tickets t" in sql:
            return _FakeResult(rows=[self._ticket_row()])
        return _FakeResult()

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True

    def _ticket_row(self):
        now = datetime.now(tz=timezone.utc)
        return {
            "ticket_key": self.ticket_key or "T-00123",
            "requester_user_id": 101,
            "requester_name": "User",
            "requester_phone": None,
            "requester_department": None,
            "category_code": self.category_code,
            "category_display_name": "Прочее",
            "status_code": self.status_code,
            "assignee_user_id": self.assignee_user_id,
            "assignee_name": self.assignee_name,
            "description": "Test",
            "created_at": now,
            "updated_at": now,
            "closed_at": None,
        }


class NormalizedTicketRepositoryTests(unittest.TestCase):
    def _repository(self, session: _FakeSession) -> PostgresNormalizedTicketRepository:
        config = TicketStorageConfig(
            backend="postgres",
            schema_mode="normalized",
            sqlite_path="",
            postgres_host="127.0.0.1",
            postgres_port=5432,
            postgres_db="test_dev_max",
            postgres_user="postgres",
            postgres_password="secret",
            postgres_sslmode="disable",
            postgres_connect_timeout_sec=5,
        )
        return PostgresNormalizedTicketRepository(
            config,
            engine=None,
            session_factory=lambda: session,
        )

    def test_create_ticket_inserts_normalized_ticket_without_pending(self) -> None:
        session = _FakeSession()
        repository = self._repository(session)

        ticket = repository._create_ticket_sync(
            requester_user_id=101,
            requester_name="User",
            category="Прочее",
            body="Test",
            requester_phone=None,
            requester_department=None,
        )

        insert_call = next(call for call in session.calls if "INSERT INTO helpdesk.tickets" in call[0])
        self.assertEqual(ticket.ticket_id, "T-00123")
        self.assertEqual(insert_call[1]["id"], 123)
        self.assertEqual(insert_call[1]["ticket_key"], "T-00123")
        self.assertNotIn("PENDING", insert_call[1].values())
        self.assertTrue(session.committed)
        self.assertTrue(session.closed)

    def test_assign_updates_status_and_assignee(self) -> None:
        session = _FakeSession()
        repository = self._repository(session)

        result = repository._assign_sync("T-00123", 202, "Specialist")

        self.assertTrue(result.ok)
        self.assertEqual(result.ticket.status, TicketStatus.IN_PROGRESS)
        self.assertEqual(result.ticket.assigned_to, 202)
        self.assertEqual(result.ticket.assignee_name, "Specialist")

    def test_close_rejects_already_closed_ticket(self) -> None:
        session = _FakeSession()
        session.status_code = "closed"
        repository = self._repository(session)

        result = repository._close_sync("T-00123", 202, "Specialist", set())

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "already_closed")
        self.assertEqual(result.ticket.status, TicketStatus.CLOSED)


if __name__ == "__main__":
    unittest.main()
