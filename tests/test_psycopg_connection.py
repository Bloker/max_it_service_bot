import sys
import types
import unittest
from unittest.mock import patch

from app.infrastructure.database.psycopg_connection import connect_utf8


class _FakeConnection:
    def __init__(self) -> None:
        self.executed: list[str] = []

    def execute(self, sql: str) -> None:
        self.executed.append(sql)


class PsycopgConnectionTests(unittest.TestCase):
    def test_connect_utf8_sets_client_encoding(self) -> None:
        fake_connection = _FakeConnection()
        fake_psycopg = types.SimpleNamespace(
            connect=lambda conninfo, **kwargs: fake_connection
        )

        with patch.dict(sys.modules, {"psycopg": fake_psycopg}):
            connection = connect_utf8("dbname=test", row_factory="dict_row")

        self.assertIs(connection, fake_connection)
        self.assertEqual(fake_connection.executed, ["SET client_encoding TO 'UTF8'"])


if __name__ == "__main__":
    unittest.main()
