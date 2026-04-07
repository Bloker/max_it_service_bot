from app.admin.services.postgres_user_access_registry import PostgresUserAccessRegistry
from app.admin.services.user_access_registry import UserAccessRegistry
from config.config import get_config


_registry: UserAccessRegistry | PostgresUserAccessRegistry | None = None


def get_user_access_registry() -> UserAccessRegistry | PostgresUserAccessRegistry:
    global _registry
    if _registry is None:
        cfg = get_config()
        if cfg.tickets.backend == "postgres":
            _registry = PostgresUserAccessRegistry(
                host=cfg.tickets.postgres_host,
                port=cfg.tickets.postgres_port,
                database=cfg.tickets.postgres_db,
                user=cfg.tickets.postgres_user,
                password=cfg.tickets.postgres_password,
                sslmode=cfg.tickets.postgres_sslmode,
                connect_timeout_sec=cfg.tickets.postgres_connect_timeout_sec,
            )
        else:
            _registry = UserAccessRegistry(cfg.bot.user_registry_path)
    return _registry
