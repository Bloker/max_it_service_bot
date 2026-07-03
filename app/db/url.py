"""Сборка SQLAlchemy URL без раскрытия секретов."""

from sqlalchemy import URL
from sqlalchemy.engine import make_url

from config.config import AppConfig, TicketStorageConfig


def make_sqlalchemy_url(cfg: AppConfig | TicketStorageConfig) -> URL:
    """Создаёт PostgreSQL SQLAlchemy URL из текущей конфигурации."""

    tickets = cfg.tickets if isinstance(cfg, AppConfig) else cfg
    return URL.create(
        drivername="postgresql+psycopg",
        username=tickets.postgres_user,
        password=tickets.postgres_password,
        host=tickets.postgres_host,
        port=tickets.postgres_port,
        database=tickets.postgres_db,
        query={
            "sslmode": tickets.postgres_sslmode,
            "connect_timeout": str(tickets.postgres_connect_timeout_sec),
        },
    )


def mask_sqlalchemy_url(url: URL | str) -> str:
    """Возвращает строку URL с замаскированным паролем."""

    if isinstance(url, URL):
        return url.render_as_string(hide_password=True)
    return make_url(str(url)).render_as_string(hide_password=True)
