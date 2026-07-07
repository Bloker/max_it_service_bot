import sys
import unittest
from unittest.mock import patch

from app.infrastructure.database.psycopg_connection import connect_postgres, connect_utf8


class _FakeConnection:
    def __init__(self) -> None:
        self.executed: list[str] = []

    def execute(self, sql: str) -> None:
        self.executed.append(sql)


class _FakePsycopg:
    def __init__(self, connection: _FakeConnection) -> None:
        self.connection = connection
        self.calls: list[tuple[str, dict]] = []

    def connect(self, conninfo: str, **kwargs):
        self.calls.append((conninfo, kwargs))
        return self.connection


class PsycopgConnectionTests(unittest.TestCase):
    def test_connect_postgres_does_not_force_client_encoding_by_default(self) -> None:
        fake_connection = _FakeConnection()
        fake_psycopg = _FakePsycopg(fake_connection)

        with patch.dict(sys.modules, {"psycopg": fake_psycopg}):
            connection = connect_postgres("dbname=test", row_factory="dict_row")

        self.assertIs(connection, fake_connection)
        self.assertEqual(
            fake_psycopg.calls,
            [("dbname=test", {"row_factory": "dict_row"})],
        )
        self.assertEqual(fake_connection.executed, [])

    def test_connect_postgres_sets_client_encoding_only_when_explicit(self) -> None:
        fake_connection = _FakeConnection()
        fake_psycopg = _FakePsycopg(fake_connection)

        with patch.dict(sys.modules, {"psycopg": fake_psycopg}):
            connection = connect_postgres(
                "dbname=test",
                row_factory="dict_row",
                client_encoding="UTF8",
            )

        self.assertIs(connection, fake_connection)
        self.assertEqual(
            fake_psycopg.calls,
            [("dbname=test", {"row_factory": "dict_row"})],
        )
        self.assertEqual(fake_connection.executed, ["SET client_encoding TO 'UTF8'"])

    def test_connect_postgres_rejects_invalid_client_encoding(self) -> None:
        fake_connection = _FakeConnection()
        fake_psycopg = _FakePsycopg(fake_connection)

        with patch.dict(sys.modules, {"psycopg": fake_psycopg}):
            with self.assertRaises(ValueError):
                connect_postgres("dbname=test", client_encoding="UTF8;RESET")

        self.assertEqual(fake_connection.executed, [])

    def test_connect_utf8_is_backward_compatible_alias(self) -> None:
        fake_connection = _FakeConnection()
        fake_psycopg = _FakePsycopg(fake_connection)

        with patch.dict(sys.modules, {"psycopg": fake_psycopg}):
            connection = connect_utf8("dbname=test", row_factory="dict_row")

        self.assertIs(connection, fake_connection)
        self.assertEqual(
            fake_psycopg.calls,
            [("dbname=test", {"row_factory": "dict_row"})],
        )
        self.assertEqual(fake_connection.executed, [])


if __name__ == "__main__":
    unittest.main()
