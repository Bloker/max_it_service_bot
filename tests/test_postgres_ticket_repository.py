import unittest
from datetime import datetime, timezone

from app.helpdesk.repositories.postgres_ticket_repository import PostgresTicketRepository


class _FakeCursor:
    def __init__(self) -> None:
        self.calls = []
        self._next_result = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "nextval(pg_get_serial_sequence" in sql:
            self._next_result = {"id": 123}
            return
        if "INSERT INTO public.helpdesk_tickets" in sql:
            now = datetime.now(tz=timezone.utc)
            self._next_result = {
                "ticket_id": params[1],
                "requester_user_id": params[2],
                "requester_name": params[3],
                "category": params[4],
                "text": params[5],
                "status": params[6],
                "assignee_user_id": None,
                "assignee_name": None,
                "created_at": now,
                "updated_at": now,
                "requester_phone": params[9],
                "requester_department": params[10],
            }

    def fetchone(self):
        return self._next_result


class _FakeConnection:
    def __init__(self) -> None:
        self.cursor_obj = _FakeCursor()
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def cursor(self):
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True


class PostgresTicketRepositoryTests(unittest.TestCase):
    def test_create_ticket_inserts_final_ticket_id_without_pending_placeholder(self) -> None:
        repository = PostgresTicketRepository(
            host="localhost",
            port=5432,
            database="test",
            user="postgres",
            password="secret",
        )
        fake_connection = _FakeConnection()
        repository._connect = lambda: fake_connection

        ticket = repository._create_ticket_sync(
            requester_user_id=101,
            requester_name="User",
            category="Прочее",
            text="Test",
            requester_phone=None,
            requester_department=None,
        )

        insert_call = next(
            call
            for call in fake_connection.cursor_obj.calls
            if "INSERT INTO public.helpdesk_tickets" in call[0]
        )

        self.assertEqual(ticket.ticket_id, "T-00123")
        self.assertEqual(insert_call[1][0], 123)
        self.assertEqual(insert_call[1][1], "T-00123")
        self.assertNotIn("PENDING", insert_call[1])
        self.assertTrue(fake_connection.committed)


if __name__ == "__main__":
    unittest.main()
