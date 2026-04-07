import logging
import os
from dataclasses import dataclass
from ipaddress import ip_network
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class LogsConfig:
    level_name: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass(frozen=True)
class BotConfig:
    token: str
    group_chat_id: int
    user_ids: tuple[int, ...]
    user_registry_path: str
    admin_ids: tuple[int, ...]
    it_specialist_ids: tuple[int, ...]
    skip_updates_on_start: bool


@dataclass(frozen=True)
class TicketStorageConfig:
    backend: str
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
    ping: bool
    dns_lookup: bool
    host_check: bool
    traceroute: bool
    nslookup: bool
    whois: bool


@dataclass(frozen=True)
class NetworkPolicyConfig:
    allowed_subnets: tuple[str, ...]
    allowed_domain_suffixes: tuple[str, ...]
    allowed_hosts: tuple[str, ...]
    allowed_device_types: tuple[str, ...]


@dataclass(frozen=True)
class NetworkToolsConfig:
    command_timeout_sec: int
    max_output_chars: int
    features: NetworkToolsFeaturesConfig
    policy: NetworkPolicyConfig


@dataclass(frozen=True)
class AppConfig:
    bot: BotConfig
    logs: LogsConfig
    tickets: TicketStorageConfig
    network_tools: NetworkToolsConfig


def _load_environment() -> None:
    root_dir = Path(__file__).resolve().parents[1]
    dotenv_candidates = (
        root_dir / ".env",
        root_dir / "config" / ".env",
    )

    for dotenv_path in dotenv_candidates:
        if dotenv_path.exists():
            load_dotenv(dotenv_path=dotenv_path, override=False)


def _parse_int_tuple_csv(raw: str, env_name: str) -> tuple[int, ...]:
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
    values = raw.strip()
    if not values:
        return ()
    return tuple(item.strip().lower() for item in values.split(",") if item.strip())


def _parse_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be a boolean value (true/false)")


def get_config() -> AppConfig:
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

    ticket_backend = os.getenv("MAX_TICKET_BACKEND", "sqlite").strip().lower()
    if ticket_backend not in {"sqlite", "memory", "postgres"}:
        raise RuntimeError("MAX_TICKET_BACKEND must be 'sqlite', 'memory' or 'postgres'")

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

    return AppConfig(
        bot=BotConfig(
            token=token,
            group_chat_id=group_chat_id,
            user_ids=user_ids,
            user_registry_path=user_registry_path,
            admin_ids=admin_ids,
            it_specialist_ids=it_specialist_ids,
            skip_updates_on_start=skip_updates_on_start,
        ),
        logs=logs,
        tickets=TicketStorageConfig(
            backend=ticket_backend,
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
    )


def setup_logging(cfg: LogsConfig) -> None:
    level = getattr(logging, (cfg.level_name or "").upper(), logging.INFO)
    logging.basicConfig(level=level, format=cfg.format, force=True)
