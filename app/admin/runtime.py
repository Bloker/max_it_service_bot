from app.admin.services.user_access_registry import UserAccessRegistry
from config.config import get_config


_registry: UserAccessRegistry | None = None


def get_user_access_registry() -> UserAccessRegistry:
    global _registry
    if _registry is None:
        cfg = get_config()
        _registry = UserAccessRegistry(cfg.bot.user_registry_path)
    return _registry
