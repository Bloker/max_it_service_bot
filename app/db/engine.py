"""Фабрики SQLAlchemy engine без подключения на import."""

from sqlalchemy import Engine, create_engine

from app.db.url import make_sqlalchemy_url
from config.config import AppConfig, TicketStorageConfig


def create_sqlalchemy_engine(
    cfg: AppConfig | TicketStorageConfig,
    *,
    echo: bool = False,
    pool_pre_ping: bool = True,
) -> Engine:
    """Создаёт sync SQLAlchemy Engine для PostgreSQL."""

    return create_engine(
        make_sqlalchemy_url(cfg),
        echo=echo,
        pool_pre_ping=pool_pre_ping,
        future=True,
    )


def dispose_sqlalchemy_engine(engine: Engine) -> None:
    """Явно закрывает pool engine."""

    engine.dispose()
