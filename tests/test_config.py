import os
import unittest
from unittest.mock import patch

from config.config import get_config


class ConfigTests(unittest.TestCase):
    def test_postgres_backend_config_parsed(self) -> None:
        env = {
            "MAX_BOT_TOKEN": "test-token",
            "MAX_GROUP_CHAT_ID": "123",
            "MAX_TICKET_BACKEND": "postgres",
            "MAX_TICKET_PG_HOST": "127.0.0.1",
            "MAX_TICKET_PG_PORT": "5432",
            "MAX_TICKET_PG_DB": "postgres",
            "MAX_TICKET_PG_USER": "postgres",
            "MAX_TICKET_PG_PASSWORD": "secret",
            "MAX_TICKET_PG_SSLMODE": "disable",
            "MAX_TICKET_PG_CONNECT_TIMEOUT_SEC": "5",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = get_config()

        self.assertEqual(cfg.tickets.backend, "postgres")
        self.assertEqual(cfg.tickets.postgres_host, "127.0.0.1")
        self.assertEqual(cfg.tickets.postgres_port, 5432)
        self.assertEqual(cfg.tickets.postgres_db, "postgres")
        self.assertEqual(cfg.tickets.postgres_user, "postgres")
        self.assertEqual(cfg.tickets.postgres_password, "secret")
        self.assertEqual(cfg.tickets.postgres_sslmode, "disable")
        self.assertEqual(cfg.tickets.postgres_connect_timeout_sec, 5)
        self.assertEqual(cfg.bot.polling_limit, 100)
        self.assertEqual(cfg.bot.polling_timeout_sec, 30)
        self.assertEqual(cfg.bot.polling_min_interval_sec, 0.55)

    def test_postgres_backend_requires_host(self) -> None:
        env = {
            "MAX_BOT_TOKEN": "test-token",
            "MAX_GROUP_CHAT_ID": "123",
            "MAX_TICKET_BACKEND": "postgres",
            "MAX_TICKET_PG_HOST": "",
            "MAX_TICKET_PG_PORT": "5432",
            "MAX_TICKET_PG_DB": "postgres",
            "MAX_TICKET_PG_USER": "postgres",
            "MAX_TICKET_PG_PASSWORD": "secret",
        }
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaises(RuntimeError):
                get_config()

    def test_polling_limit_rejects_values_above_max_requirements(self) -> None:
        env = {
            "MAX_BOT_TOKEN": "test-token",
            "MAX_GROUP_CHAT_ID": "123",
            "MAX_POLLING_LIMIT": "101",
        }
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaises(RuntimeError):
                get_config()


if __name__ == "__main__":
    unittest.main()
