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
            "MAX_WIFI_LINK_EMAIL": "",
            "MAX_WIFI_LINK_PASSWORD": "",
            "MAX_WIFI_LINK_MAX_PAGES": "20",
            "MAX_NETARIUM_API_KEY": "",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = get_config()

        self.assertEqual(cfg.tickets.backend, "postgres")
        self.assertEqual(cfg.tickets.schema_mode, "legacy")
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
        self.assertEqual(cfg.wifi_link.base_url, "https://lk.wi-fi.link")
        self.assertEqual(cfg.wifi_link.timeout_sec, 10)
        self.assertEqual(cfg.wifi_link.max_pages, 20)
        self.assertEqual(cfg.wifi_link.cache_ttl_sec, 120)
        self.assertFalse(cfg.wifi_link.is_configured)
        self.assertEqual(cfg.netarium.base_url, "http://192.168.2.34:8081")
        self.assertEqual(cfg.netarium.object_class, "61746224-5eac-4663-a7db-396beffec01c")
        self.assertEqual(cfg.netarium.timeout_sec, 10)
        self.assertEqual(cfg.netarium.cache_ttl_sec, 120)
        self.assertFalse(cfg.netarium.is_configured)
        self.assertTrue(cfg.observability.audit_enabled)
        self.assertTrue(cfg.observability.ticket_events_enabled)
        self.assertTrue(cfg.observability.network_tool_runs_enabled)
        self.assertEqual(cfg.media.storage_root, "./data/media")
        self.assertEqual(cfg.media.collection_window_sec, 15)
        self.assertEqual(cfg.media.max_attachments_per_item, 10)
        self.assertEqual(cfg.media.max_file_size_mb, 50)
        self.assertEqual(cfg.max_api.max_attempts, 4)
        self.assertEqual(cfg.max_api.base_delay_sec, 0.5)
        self.assertEqual(cfg.max_api.max_delay_sec, 5.0)
        self.assertEqual(cfg.max_api.jitter_sec, 0.25)
        self.assertEqual(cfg.max_api.server_error_attempts, 2)
        self.assertEqual(cfg.max_api.edit_min_interval_sec, 1.0)
        self.assertTrue(cfg.tls_reminder.enabled)
        self.assertEqual(cfg.tls_reminder.host, "max.myservicedomain.ru")
        self.assertEqual(cfg.tls_reminder.port, 443)
        self.assertEqual(cfg.tls_reminder.reminder_days, 5)
        self.assertEqual(cfg.tls_reminder.interval_sec, 86400)
        self.assertEqual(cfg.tls_reminder.timeout_sec, 10)
        self.assertEqual(cfg.tls_reminder.server_hint, "192.168.1.177")

    def test_tls_reminder_custom_config_parsed(self) -> None:
        env = {
            "MAX_BOT_TOKEN": "test-token",
            "MAX_GROUP_CHAT_ID": "123",
            "MAX_TLS_REMINDER_ENABLED": "false",
            "MAX_TLS_REMINDER_HOST": "tls.example.test",
            "MAX_TLS_REMINDER_PORT": "8443",
            "MAX_TLS_REMINDER_DAYS": "7",
            "MAX_TLS_REMINDER_INTERVAL_SEC": "172800",
            "MAX_TLS_REMINDER_TIMEOUT_SEC": "3",
            "MAX_TLS_REMINDER_SERVER_HINT": "",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = get_config()

        self.assertFalse(cfg.tls_reminder.enabled)
        self.assertEqual(cfg.tls_reminder.host, "tls.example.test")
        self.assertEqual(cfg.tls_reminder.port, 8443)
        self.assertEqual(cfg.tls_reminder.reminder_days, 7)
        self.assertEqual(cfg.tls_reminder.interval_sec, 172800)
        self.assertEqual(cfg.tls_reminder.timeout_sec, 3)
        self.assertEqual(cfg.tls_reminder.server_hint, "")

    def test_tls_reminder_rejects_interval_below_one_day(self) -> None:
        env = {
            "MAX_BOT_TOKEN": "test-token",
            "MAX_GROUP_CHAT_ID": "123",
            "MAX_TLS_REMINDER_INTERVAL_SEC": "3600",
        }
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaises(RuntimeError):
                get_config()

    def test_max_api_retry_custom_config_parsed(self) -> None:
        env = {
            "MAX_BOT_TOKEN": "test-token",
            "MAX_GROUP_CHAT_ID": "123",
            "MAX_API_RETRY_MAX_ATTEMPTS": "5",
            "MAX_API_RETRY_BASE_DELAY_SEC": "0.2",
            "MAX_API_RETRY_MAX_DELAY_SEC": "3.5",
            "MAX_API_RETRY_JITTER_SEC": "0.1",
            "MAX_API_RETRY_5XX_ATTEMPTS": "3",
            "MAX_MESSAGE_EDIT_MIN_INTERVAL_SEC": "0.7",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = get_config()

        self.assertEqual(cfg.max_api.max_attempts, 5)
        self.assertEqual(cfg.max_api.base_delay_sec, 0.2)
        self.assertEqual(cfg.max_api.max_delay_sec, 3.5)
        self.assertEqual(cfg.max_api.jitter_sec, 0.1)
        self.assertEqual(cfg.max_api.server_error_attempts, 3)
        self.assertEqual(cfg.max_api.edit_min_interval_sec, 0.7)

    def test_max_api_retry_rejects_invalid_values(self) -> None:
        env = {
            "MAX_BOT_TOKEN": "test-token",
            "MAX_GROUP_CHAT_ID": "123",
            "MAX_API_RETRY_MAX_ATTEMPTS": "0",
        }
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaises(RuntimeError):
                get_config()

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

    def test_ticket_schema_mode_accepts_normalized_for_postgres(self) -> None:
        env = {
            "MAX_BOT_TOKEN": "test-token",
            "MAX_GROUP_CHAT_ID": "123",
            "MAX_TICKET_BACKEND": "postgres",
            "MAX_TICKET_SCHEMA_MODE": "normalized",
            "MAX_TICKET_PG_HOST": "127.0.0.1",
            "MAX_TICKET_PG_PORT": "5432",
            "MAX_TICKET_PG_DB": "test_dev_max",
            "MAX_TICKET_PG_USER": "postgres",
            "MAX_TICKET_PG_PASSWORD": "secret",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = get_config()

        self.assertEqual(cfg.tickets.schema_mode, "normalized")

    def test_ticket_schema_mode_rejects_unknown_value(self) -> None:
        env = {
            "MAX_BOT_TOKEN": "test-token",
            "MAX_GROUP_CHAT_ID": "123",
            "MAX_TICKET_SCHEMA_MODE": "bad",
        }
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaises(RuntimeError):
                get_config()

    def test_ticket_schema_mode_requires_postgres_for_normalized(self) -> None:
        env = {
            "MAX_BOT_TOKEN": "test-token",
            "MAX_GROUP_CHAT_ID": "123",
            "MAX_TICKET_BACKEND": "sqlite",
            "MAX_TICKET_SCHEMA_MODE": "normalized",
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
