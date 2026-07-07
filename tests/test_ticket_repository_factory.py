import unittest
from unittest.mock import patch

from app.helpdesk.repositories.postgres_normalized_ticket_repository import (
    PostgresNormalizedTicketRepository,
)
from app.helpdesk.repositories.postgres_ticket_repository import PostgresTicketRepository
from app.helpdesk.repositories.shadow_ticket_repository import ShadowReadTicketRepository
from app.helpdesk.runtime import _build_ticket_service
from config.config import (
    AppConfig,
    BotConfig,
    LogsConfig,
    MaxApiRetryConfig,
    NetariumConfig,
    NetworkPolicyConfig,
    NetworkToolsConfig,
    NetworkToolsFeaturesConfig,
    ObservabilityConfig,
    TicketStorageConfig,
    WifiLinkConfig,
)


def _config(schema_mode: str) -> AppConfig:
    return AppConfig(
        bot=BotConfig(
            token="token",
            group_chat_id=123,
            user_ids=(),
            user_registry_path="data/users.json",
            admin_ids=(),
            it_specialist_ids=(),
            skip_updates_on_start=True,
            polling_limit=100,
            polling_timeout_sec=30,
            polling_min_interval_sec=0.55,
        ),
        max_api=MaxApiRetryConfig(),
        logs=LogsConfig(),
        tickets=TicketStorageConfig(
            backend="postgres",
            schema_mode=schema_mode,
            sqlite_path="",
            postgres_host="127.0.0.1",
            postgres_port=5432,
            postgres_db="test_dev_max",
            postgres_user="postgres",
            postgres_password="secret",
            postgres_sslmode="disable",
            postgres_connect_timeout_sec=5,
        ),
        network_tools=NetworkToolsConfig(
            command_timeout_sec=5,
            max_output_chars=2000,
            features=NetworkToolsFeaturesConfig(
                ping=True,
                dns_lookup=True,
                host_check=True,
                traceroute=True,
                nslookup=True,
                whois=False,
            ),
            policy=NetworkPolicyConfig(
                allowed_subnets=("192.168.0.0/16",),
                allowed_domain_suffixes=(),
                allowed_hosts=(),
                allowed_device_types=(),
            ),
        ),
        wifi_link=WifiLinkConfig(
            base_url="https://lk.wi-fi.link",
            email="",
            password="",
            timeout_sec=10,
            max_pages=20,
            cache_ttl_sec=120,
        ),
        netarium=NetariumConfig(
            base_url="http://192.168.2.34:8081",
            api_key="",
            object_class="class",
            timeout_sec=10,
            cache_ttl_sec=120,
        ),
        observability=ObservabilityConfig(
            audit_enabled=False,
            ticket_events_enabled=False,
            network_tool_runs_enabled=False,
        ),
    )


class TicketRepositoryFactoryTests(unittest.TestCase):
    def test_legacy_schema_mode_builds_legacy_postgres_repository(self) -> None:
        with patch("app.helpdesk.runtime.get_config", return_value=_config("legacy")):
            service = _build_ticket_service()

        self.assertIsInstance(service.repository, PostgresTicketRepository)

    def test_normalized_schema_mode_builds_normalized_repository(self) -> None:
        with patch("app.helpdesk.runtime.get_config", return_value=_config("normalized")):
            service = _build_ticket_service()

        self.assertIsInstance(service.repository, PostgresNormalizedTicketRepository)
        service.repository.close_engine()

    def test_shadow_read_schema_mode_wraps_legacy_and_normalized(self) -> None:
        with patch("app.helpdesk.runtime.get_config", return_value=_config("shadow_read")):
            service = _build_ticket_service()

        self.assertIsInstance(service.repository, ShadowReadTicketRepository)


if __name__ == "__main__":
    unittest.main()
