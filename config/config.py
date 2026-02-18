import os
import logging
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass(frozen=True)
class LogsConfig:
    level_name: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass(frozen=True)
class BotConfig:
    token: str
    group_chat_id: int


@dataclass(frozen=True)
class AppConfig:
    bot: BotConfig
    logs: LogsConfig


def get_config() -> AppConfig:
    load_dotenv()

    token = os.getenv("MAX_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Токен бота не найден! Установите MAX_BOT_TOKEN в .env")

    group_chat_id_raw = os.getenv("MAX_GROUP_CHAT_ID", "").strip()
    if not group_chat_id_raw:
        raise RuntimeError("ID группового чата не найден! Установите MAX_GROUP_CHAT_ID в .env")

    try:
        group_chat_id = str(group_chat_id_raw)
    except ValueError:
        raise RuntimeError("MAX_GROUP_CHAT_ID должен быть числом (chat_id)")

    logs = LogsConfig(
        level_name=os.getenv("LOG_LEVEL", "INFO").strip(),
        format=os.getenv("LOG_FORMAT", LogsConfig.format),
    )

    return AppConfig(
        bot=BotConfig(token=token, group_chat_id=group_chat_id),
        logs=logs,
    )


def setup_logging(cfg: LogsConfig) -> None:
    level = getattr(logging, (cfg.level_name or "").upper(), logging.INFO)
    logging.basicConfig(level=level, format=cfg.format, force=True)