"""Инициализация MAX Bot API, dispatcher и long polling."""

import asyncio
import logging
from time import monotonic

from maxapi import Bot, Dispatcher

from app.bot.handlers import routes
from config.config import BotConfig
from config.config import get_config

logger = logging.getLogger(__name__)


def register_routes(dp: Dispatcher) -> None:
    """Регистрирует все обработчики событий MAX в диспетчере."""

    for reg in routes:
        reg(dp)


def configure_long_polling_limits(bot: Bot, cfg: BotConfig) -> None:
    """Ограничивает long polling под текущие требования MAX API."""

    original_get_updates = bot.get_updates
    last_request_at = 0.0

    async def get_updates_with_limits(*, limit=None, timeout=None, marker=None, types=None):
        nonlocal last_request_at

        # MAX ограничивает частоту запросов; выдерживаем паузу между poll.
        elapsed = monotonic() - last_request_at
        if elapsed < cfg.polling_min_interval_sec:
            await asyncio.sleep(cfg.polling_min_interval_sec - elapsed)

        last_request_at = monotonic()
        return await original_get_updates(
            limit=limit if limit is not None else cfg.polling_limit,
            timeout=timeout if timeout is not None else cfg.polling_timeout_sec,
            marker=marker,
            types=types,
        )

    bot.get_updates = get_updates_with_limits


async def main() -> None:
    """Создает бота, настраивает polling и запускает обработку событий."""

    cfg = get_config()

    bot = Bot(token=cfg.bot.token)
    configure_long_polling_limits(bot, cfg.bot)
    dp = Dispatcher()

    register_routes(dp)

    logger.info("Бот запускается...")

    try:
        await bot.delete_webhook()
    except Exception as exc:
        logger.warning("Ошибка удаления webhook: %s", exc)

    logger.info(
        "Бот запущен и ожидает сообщений: polling_limit=%s polling_timeout=%s polling_min_interval=%s",
        cfg.bot.polling_limit,
        cfg.bot.polling_timeout_sec,
        cfg.bot.polling_min_interval_sec,
    )
    await dp.start_polling(bot, skip_updates=cfg.bot.skip_updates_on_start)
