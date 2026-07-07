"""Загрузка и валидация конфигурации приложения из окружения."""

import logging
import os
from dataclasses import dataclass
from ipaddress import ip_network
from pathlib import Path

from dotenv import load_dotenv

from app.bot.services.max_api_retry import MaxApiRetryConfig


@dataclass(frozen=True)
class LogsConfig:
    """Настройки логирования приложения."""

    level_name: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass(frozen=True)
class BotConfig:
    """Настройки MAX-бота, polling и webhook."""

    token: str
    group_chat_id: int
    user_ids: tuple[int, ...]
    user_registry_path: str
    admin_ids: tuple[int, ...]
    it_specialist_ids: tuple[int, ...]
    skip_updates_on_start: bool
    polling_limit: int
    polling_timeout_sec: int
    polling_min_interval_sec: float
    update_mode: str = "longpoll"
    webhook_host: str = "127.0.0.1"
    webhook_port: int = 8080
    webhook_path: str = "/max-webhook"
    webhook_health_path: str = "/health"
    webhook_secret: str = ""


@dataclass(frozen=True)
class TicketStorageConfig:
    """Настройки хранилища заявок HelpDesk."""

    backend: str
    schema_mode: str
    sqlite_path: str
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    postgres_sslmode: str
    postgres_connect_timeout_sec: int


@dataclass(frozen=True)
class NetworkToolsFeaturesConfig:
    """Флаги доступности сетевых инструментов."""

    ping: bool
    dns_lookup: bool
    host_check: bool
    traceroute: bool
    nslookup: bool
    whois: bool


@dataclass(frozen=True)
class NetworkPolicyConfig:
    """Ограничения сетевой диагностики по корпоративной политике."""

    allowed_subnets: tuple[str, ...]
    allowed_domain_suffixes: tuple[str, ...]
    allowed_hosts: tuple[str, ...]
    allowed_device_types: tuple[str, ...]


@dataclass(frozen=True)
class NetworkToolsConfig:
    """Общие настройки сетевых инструментов."""

    command_timeout_sec: int
    max_output_chars: int
    features: NetworkToolsFeaturesConfig
    policy: NetworkPolicyConfig


@dataclass(frozen=True)
class WifiLinkConfig:
    """Настройки интеграции с личным кабинетом WiFi.link."""

    base_url: str
    email: str
    password: str
    timeout_sec: int
    max_pages: int
    cache_ttl_sec: int

    @property
    def is_configured(self) -> bool:
        """Проверяет, заданы ли учетные данные WiFi.link."""

        return bool(self.email and self.password)


@dataclass(frozen=True)
class NetariumConfig:
    """Настройки интеграции с Netarium API."""

    base_url: str
    api_key: str
    object_class: str
    timeout_sec: int
    cache_ttl_sec: int

    @property
    def is_configured(self) -> bool:
        """Проверяет, достаточно ли данных для запроса Netarium API."""

        return bool(self.base_url and self.api_key and self.object_class)


@dataclass(frozen=True)
class ObservabilityConfig:
    """Флаги audit/events/observability."""

    audit_enabled: bool
    ticket_events_enabled: bool
    network_tool_runs_enabled: bool


@dataclass(frozen=True)
class AppConfig:
    """Полная конфигурация приложения."""

    bot: BotConfig
    max_api: MaxApiRetryConfig
    logs: LogsConfig
    tickets: TicketStorageConfig
    network_tools: NetworkToolsConfig
    wifi_link: WifiLinkConfig
    netarium: NetariumConfig
    observability: ObservabilityConfig


def _load_environment() -> None:
    """Загружает .env из корня проекта и config/.env."""

    root_dir = Path(__file__).resolve().parents[1]
    dotenv_candidates = (
        root_dir / ".env",
        root_dir / "config" / ".env",
    )

    for dotenv_path in dotenv_candidates:
        if dotenv_path.exists():
            load_dotenv(dotenv_path=dotenv_path, override=False)


def _parse_int_tuple_csv(raw: str, env_name: str) -> tuple[int, ...]:
    """Парсит CSV-строку с integer ID."""

    values = raw.strip()
    if not values:
        return ()

    parsed_ids: list[int] = []
    for item in values.split(","):
        value = item.strip()
        if not value:
            continue
        try:
            parsed_ids.append(int(value))
        except ValueError as exc:
            raise RuntimeError(f"{env_name} must contain integer IDs separated by commas") from exc
    return tuple(parsed_ids)


def _parse_str_tuple_csv(raw: str) -> tuple[str, ...]:
    """Парсит CSV-строку в tuple lower-case значений."""

    values = raw.strip()
    if not values:
        return ()
    return tuple(item.strip().lower() for item in values.split(",") if item.strip())


def _parse_bool_env(name: str, default: bool) -> bool:
    """Парсит boolean env-переменную с явной валидацией."""

    raw = os.getenv(name, str(default)).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be a boolean value (true/false)")


def _parse_float_env(name: str, default: float) -> float:
    """Парсит float env-переменную с понятной ошибкой."""

    raw = os.getenv(name, str(default)).strip()
    try:
        return float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc


def _parse_int_env(name: str, default: int) -> int:
    """Парсит integer env-переменную с понятной ошибкой."""

    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def get_config() -> AppConfig:
    """Собирает и валидирует конфигурацию из переменных окружения."""

    _load_environment()

    token = os.getenv("MAX_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Bot token is missing. Set MAX_BOT_TOKEN in .env")

    group_chat_id_raw = os.getenv("MAX_GROUP_CHAT_ID", "").strip()
    if not group_chat_id_raw:
        raise RuntimeError("Group chat ID is missing. Set MAX_GROUP_CHAT_ID in .env")

    try:
        group_chat_id = int(group_chat_id_raw)
    except ValueError as exc:
        raise RuntimeError("MAX_GROUP_CHAT_ID must be an integer chat_id") from exc

    logs = LogsConfig(
        level_name=os.getenv("LOG_LEVEL", "INFO").strip(),
        format=os.getenv("LOG_FORMAT", LogsConfig.format),
    )

    admin_ids = _parse_int_tuple_csv(os.getenv("MAX_ADMIN_IDS", ""), "MAX_ADMIN_IDS")
    user_ids = _parse_int_tuple_csv(os.getenv("MAX_USER_IDS", ""), "MAX_USER_IDS")
    user_registry_path = os.getenv(
        "MAX_USER_REGISTRY_PATH",
        "data/user_access_registry.json",
    ).strip()
    if not user_registry_path:
        raise RuntimeError("MAX_USER_REGISTRY_PATH must not be empty")
    it_specialist_ids = _parse_int_tuple_csv(
        os.getenv("MAX_IT_SPECIALIST_IDS", ""),
        "MAX_IT_SPECIALIST_IDS",
    )
    skip_updates_on_start = _parse_bool_env("MAX_SKIP_UPDATES_ON_START", True)
    polling_limit_raw = os.getenv("MAX_POLLING_LIMIT", "100").strip()
    polling_timeout_raw = os.getenv("MAX_POLLING_TIMEOUT_SEC", "30").strip()
    try:
        polling_limit = int(polling_limit_raw)
        polling_timeout_sec = int(polling_timeout_raw)
    except ValueError as exc:
        raise RuntimeError("MAX_POLLING_LIMIT and MAX_POLLING_TIMEOUT_SEC must be integers") from exc

    if not (1 <= polling_limit <= 100):
        raise RuntimeError("MAX_POLLING_LIMIT must be between 1 and 100")
    if not (0 <= polling_timeout_sec <= 30):
        raise RuntimeError("MAX_POLLING_TIMEOUT_SEC must be between 0 and 30")

    polling_min_interval_sec = _parse_float_env("MAX_POLLING_MIN_INTERVAL_SEC", 0.55)
    if polling_min_interval_sec < 0.5:
        raise RuntimeError("MAX_POLLING_MIN_INTERVAL_SEC must be >= 0.5")

    update_mode = os.getenv("MAX_UPDATE_MODE", "longpoll").strip().lower()
    if update_mode not in {"longpoll", "webhook"}:
        raise RuntimeError("MAX_UPDATE_MODE must be 'longpoll' or 'webhook'")

    webhook_host = os.getenv("MAX_WEBHOOK_HOST", "127.0.0.1").strip()
    if not webhook_host:
        raise RuntimeError("MAX_WEBHOOK_HOST must not be empty")

    webhook_port_raw = os.getenv("MAX_WEBHOOK_PORT", "8080").strip()
    try:
        webhook_port = int(webhook_port_raw)
    except ValueError as exc:
        raise RuntimeError("MAX_WEBHOOK_PORT must be an integer") from exc
    if not (1 <= webhook_port <= 65535):
        raise RuntimeError("MAX_WEBHOOK_PORT must be between 1 and 65535")

    webhook_path = os.getenv("MAX_WEBHOOK_PATH", "/max-webhook").strip()
    webhook_health_path = os.getenv("MAX_WEBHOOK_HEALTH_PATH", "/health").strip()
    if not webhook_path.startswith("/"):
        raise RuntimeError("MAX_WEBHOOK_PATH must start with '/'")
    if not webhook_health_path.startswith("/"):
        raise RuntimeError("MAX_WEBHOOK_HEALTH_PATH must start with '/'")
    if webhook_path == webhook_health_path:
        raise RuntimeError("MAX_WEBHOOK_PATH and MAX_WEBHOOK_HEALTH_PATH must be different")
    webhook_secret = os.getenv("MAX_WEBHOOK_SECRET", "").strip()

    max_api_retry_attempts = _parse_int_env("MAX_API_RETRY_MAX_ATTEMPTS", 4)
    max_api_retry_base_delay = _parse_float_env("MAX_API_RETRY_BASE_DELAY_SEC", 0.5)
    max_api_retry_max_delay = _parse_float_env("MAX_API_RETRY_MAX_DELAY_SEC", 5.0)
    max_api_retry_jitter = _parse_float_env("MAX_API_RETRY_JITTER_SEC", 0.25)
    max_api_retry_5xx_attempts = _parse_int_env("MAX_API_RETRY_5XX_ATTEMPTS", 2)
    max_message_edit_min_interval = _parse_float_env(
        "MAX_MESSAGE_EDIT_MIN_INTERVAL_SEC",
        1.0,
    )
    if max_api_retry_attempts < 1:
        raise RuntimeError("MAX_API_RETRY_MAX_ATTEMPTS must be >= 1")
    if max_api_retry_5xx_attempts < 1:
        raise RuntimeError("MAX_API_RETRY_5XX_ATTEMPTS must be >= 1")
    if max_api_retry_base_delay < 0:
        raise RuntimeError("MAX_API_RETRY_BASE_DELAY_SEC must be >= 0")
    if max_api_retry_max_delay < 0:
        raise RuntimeError("MAX_API_RETRY_MAX_DELAY_SEC must be >= 0")
    if max_api_retry_jitter < 0:
        raise RuntimeError("MAX_API_RETRY_JITTER_SEC must be >= 0")
    if max_message_edit_min_interval < 0:
        raise RuntimeError("MAX_MESSAGE_EDIT_MIN_INTERVAL_SEC must be >= 0")

    max_api = MaxApiRetryConfig(
        max_attempts=max_api_retry_attempts,
        base_delay_sec=max_api_retry_base_delay,
        max_delay_sec=max_api_retry_max_delay,
        jitter_sec=max_api_retry_jitter,
        server_error_attempts=max_api_retry_5xx_attempts,
        edit_min_interval_sec=max_message_edit_min_interval,
    )

    ticket_backend = os.getenv("MAX_TICKET_BACKEND", "sqlite").strip().lower()
    if ticket_backend not in {"sqlite", "memory", "postgres"}:
        raise RuntimeError("MAX_TICKET_BACKEND must be 'sqlite', 'memory' or 'postgres'")

    ticket_schema_mode = os.getenv("MAX_TICKET_SCHEMA_MODE", "legacy").strip().lower()
    if ticket_schema_mode not in {"legacy", "shadow_read", "normalized"}:
        raise RuntimeError(
            "MAX_TICKET_SCHEMA_MODE must be 'legacy', 'shadow_read' or 'normalized'"
        )
    if ticket_backend != "postgres" and ticket_schema_mode != "legacy":
        raise RuntimeError(
            "MAX_TICKET_SCHEMA_MODE can be 'shadow_read' or 'normalized' only with postgres backend"
        )

    ticket_sqlite_path = os.getenv("MAX_TICKET_DB_PATH", "data/helpdesk_tickets.sqlite3").strip()
    if not ticket_sqlite_path:
        raise RuntimeError("MAX_TICKET_DB_PATH must not be empty")

    ticket_pg_host = os.getenv("MAX_TICKET_PG_HOST", "").strip()
    ticket_pg_port_raw = os.getenv("MAX_TICKET_PG_PORT", "5432").strip()
    ticket_pg_db = os.getenv("MAX_TICKET_PG_DB", "postgres").strip()
    ticket_pg_user = os.getenv("MAX_TICKET_PG_USER", "").strip()
    ticket_pg_password = os.getenv("MAX_TICKET_PG_PASSWORD", "").strip()
    ticket_pg_sslmode = os.getenv("MAX_TICKET_PG_SSLMODE", "prefer").strip().lower() or "prefer"
    ticket_pg_timeout_raw = os.getenv("MAX_TICKET_PG_CONNECT_TIMEOUT_SEC", "5").strip()

    try:
        ticket_pg_port = int(ticket_pg_port_raw)
        ticket_pg_connect_timeout_sec = int(ticket_pg_timeout_raw)
    except ValueError as exc:
        raise RuntimeError(
            "MAX_TICKET_PG_PORT and MAX_TICKET_PG_CONNECT_TIMEOUT_SEC must be integers"
        ) from exc

    if not (1 <= ticket_pg_port <= 65535):
        raise RuntimeError("MAX_TICKET_PG_PORT must be between 1 and 65535")
    if ticket_pg_connect_timeout_sec <= 0:
        raise RuntimeError("MAX_TICKET_PG_CONNECT_TIMEOUT_SEC must be > 0")

    allowed_sslmodes = {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}
    if ticket_pg_sslmode not in allowed_sslmodes:
        raise RuntimeError(
            "MAX_TICKET_PG_SSLMODE must be one of: "
            "disable, allow, prefer, require, verify-ca, verify-full"
        )

    if ticket_backend == "postgres":
        if not ticket_pg_host:
            raise RuntimeError("MAX_TICKET_PG_HOST must not be empty for postgres backend")
        if not ticket_pg_db:
            raise RuntimeError("MAX_TICKET_PG_DB must not be empty for postgres backend")
        if not ticket_pg_user:
            raise RuntimeError("MAX_TICKET_PG_USER must not be empty for postgres backend")
        if not ticket_pg_password:
            raise RuntimeError("MAX_TICKET_PG_PASSWORD must not be empty for postgres backend")

    allowed_subnets = _parse_str_tuple_csv(
        os.getenv("MAX_NET_ALLOWED_SUBNETS", "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16")
    )
    for subnet in allowed_subnets:
        try:
            ip_network(subnet, strict=False)
        except ValueError as exc:
            raise RuntimeError(f"MAX_NET_ALLOWED_SUBNETS has invalid subnet: {subnet}") from exc

    allowed_domain_suffixes = _parse_str_tuple_csv(
        os.getenv("MAX_NET_ALLOWED_DOMAIN_SUFFIXES", ".corp.local,.internal")
    )
    allowed_hosts = _parse_str_tuple_csv(os.getenv("MAX_NET_ALLOWED_HOSTS", ""))
    allowed_device_types = _parse_str_tuple_csv(
        os.getenv("MAX_NET_ALLOWED_DEVICE_TYPES", "android_tv,tv_box,printer,router,switch,pc")
    )

    timeout_raw = os.getenv("MAX_NET_COMMAND_TIMEOUT_SEC", "5").strip()
    output_raw = os.getenv("MAX_NET_MAX_OUTPUT_CHARS", "2000").strip()
    try:
        timeout_sec = int(timeout_raw)
        max_output_chars = int(output_raw)
    except ValueError as exc:
        raise RuntimeError("MAX_NET_COMMAND_TIMEOUT_SEC and MAX_NET_MAX_OUTPUT_CHARS must be integers") from exc

    if timeout_sec <= 0:
        raise RuntimeError("MAX_NET_COMMAND_TIMEOUT_SEC must be > 0")
    if max_output_chars < 500:
        raise RuntimeError("MAX_NET_MAX_OUTPUT_CHARS must be >= 500")

    features = NetworkToolsFeaturesConfig(
        ping=_parse_bool_env("MAX_NET_FEATURE_PING", True),
        dns_lookup=_parse_bool_env("MAX_NET_FEATURE_DNS_LOOKUP", True),
        host_check=_parse_bool_env("MAX_NET_FEATURE_HOST_CHECK", True),
        traceroute=_parse_bool_env("MAX_NET_FEATURE_TRACEROUTE", True),
        nslookup=_parse_bool_env("MAX_NET_FEATURE_NSLOOKUP", True),
        whois=_parse_bool_env("MAX_NET_FEATURE_WHOIS", False),
    )

    # WiFi.link используется только в административном WiFi-сценарии.
    wifi_link_base_url = os.getenv("MAX_WIFI_LINK_BASE_URL", "https://lk.wi-fi.link").strip()
    wifi_link_email = os.getenv("MAX_WIFI_LINK_EMAIL", "").strip()
    wifi_link_password = os.getenv("MAX_WIFI_LINK_PASSWORD", "").strip()
    wifi_link_timeout_raw = os.getenv("MAX_WIFI_LINK_TIMEOUT_SEC", "10").strip()
    wifi_link_max_pages_raw = os.getenv("MAX_WIFI_LINK_MAX_PAGES", "20").strip()
    wifi_link_cache_ttl_raw = os.getenv("MAX_WIFI_LINK_CACHE_TTL_SEC", "120").strip()
    try:
        wifi_link_timeout_sec = int(wifi_link_timeout_raw)
        wifi_link_max_pages = int(wifi_link_max_pages_raw)
        wifi_link_cache_ttl_sec = int(wifi_link_cache_ttl_raw)
    except ValueError as exc:
        raise RuntimeError(
            "MAX_WIFI_LINK_TIMEOUT_SEC, MAX_WIFI_LINK_MAX_PAGES and "
            "MAX_WIFI_LINK_CACHE_TTL_SEC must be integers"
        ) from exc

    if not wifi_link_base_url:
        raise RuntimeError("MAX_WIFI_LINK_BASE_URL must not be empty")
    if wifi_link_timeout_sec <= 0:
        raise RuntimeError("MAX_WIFI_LINK_TIMEOUT_SEC must be > 0")
    if wifi_link_max_pages <= 0:
        raise RuntimeError("MAX_WIFI_LINK_MAX_PAGES must be > 0")
    if wifi_link_cache_ttl_sec < 0:
        raise RuntimeError("MAX_WIFI_LINK_CACHE_TTL_SEC must be >= 0")

    # Netarium служит источником списка комнат и данных проживания гостей.
    netarium_base_url = os.getenv("MAX_NETARIUM_BASE_URL", "http://192.168.2.34:8081").strip()
    netarium_api_key = os.getenv("MAX_NETARIUM_API_KEY", "").strip()
    netarium_object_class = os.getenv(
        "MAX_NETARIUM_OBJECT_CLASS",
        "61746224-5eac-4663-a7db-396beffec01c",
    ).strip()
    netarium_timeout_raw = os.getenv("MAX_NETARIUM_TIMEOUT_SEC", "10").strip()
    netarium_cache_ttl_raw = os.getenv("MAX_NETARIUM_CACHE_TTL_SEC", "120").strip()
    try:
        netarium_timeout_sec = int(netarium_timeout_raw)
        netarium_cache_ttl_sec = int(netarium_cache_ttl_raw)
    except ValueError as exc:
        raise RuntimeError(
            "MAX_NETARIUM_TIMEOUT_SEC and MAX_NETARIUM_CACHE_TTL_SEC must be integers"
        ) from exc

    if not netarium_base_url:
        raise RuntimeError("MAX_NETARIUM_BASE_URL must not be empty")
    if not netarium_object_class:
        raise RuntimeError("MAX_NETARIUM_OBJECT_CLASS must not be empty")
    if netarium_timeout_sec <= 0:
        raise RuntimeError("MAX_NETARIUM_TIMEOUT_SEC must be > 0")
    if netarium_cache_ttl_sec < 0:
        raise RuntimeError("MAX_NETARIUM_CACHE_TTL_SEC must be >= 0")

    observability = ObservabilityConfig(
        audit_enabled=_parse_bool_env("MAX_AUDIT_ENABLED", True),
        ticket_events_enabled=_parse_bool_env("MAX_TICKET_EVENTS_ENABLED", True),
        network_tool_runs_enabled=_parse_bool_env("MAX_NETWORK_TOOL_RUNS_ENABLED", True),
    )

    return AppConfig(
        bot=BotConfig(
            token=token,
            group_chat_id=group_chat_id,
            user_ids=user_ids,
            user_registry_path=user_registry_path,
            admin_ids=admin_ids,
            it_specialist_ids=it_specialist_ids,
            skip_updates_on_start=skip_updates_on_start,
            polling_limit=polling_limit,
            polling_timeout_sec=polling_timeout_sec,
            polling_min_interval_sec=polling_min_interval_sec,
            update_mode=update_mode,
            webhook_host=webhook_host,
            webhook_port=webhook_port,
            webhook_path=webhook_path,
            webhook_health_path=webhook_health_path,
            webhook_secret=webhook_secret,
        ),
        max_api=max_api,
        logs=logs,
        tickets=TicketStorageConfig(
            backend=ticket_backend,
            schema_mode=ticket_schema_mode,
            sqlite_path=ticket_sqlite_path,
            postgres_host=ticket_pg_host,
            postgres_port=ticket_pg_port,
            postgres_db=ticket_pg_db,
            postgres_user=ticket_pg_user,
            postgres_password=ticket_pg_password,
            postgres_sslmode=ticket_pg_sslmode,
            postgres_connect_timeout_sec=ticket_pg_connect_timeout_sec,
        ),
        network_tools=NetworkToolsConfig(
            command_timeout_sec=timeout_sec,
            max_output_chars=max_output_chars,
            features=features,
            policy=NetworkPolicyConfig(
                allowed_subnets=allowed_subnets,
                allowed_domain_suffixes=allowed_domain_suffixes,
                allowed_hosts=allowed_hosts,
                allowed_device_types=allowed_device_types,
            ),
        ),
        wifi_link=WifiLinkConfig(
            base_url=wifi_link_base_url.rstrip("/"),
            email=wifi_link_email,
            password=wifi_link_password,
            timeout_sec=wifi_link_timeout_sec,
            max_pages=wifi_link_max_pages,
            cache_ttl_sec=wifi_link_cache_ttl_sec,
        ),
        netarium=NetariumConfig(
            base_url=netarium_base_url.rstrip("/"),
            api_key=netarium_api_key,
            object_class=netarium_object_class,
            timeout_sec=netarium_timeout_sec,
            cache_ttl_sec=netarium_cache_ttl_sec,
        ),
        observability=observability,
    )


def setup_logging(cfg: LogsConfig) -> None:
    """Настраивает root logging для всего приложения."""

    level = getattr(logging, (cfg.level_name or "").upper(), logging.INFO)
    logging.basicConfig(level=level, format=cfg.format, force=True)
