import logging

from maxapi import Bot, Dispatcher

from app.bot.handlers import routes
from config.config import get_config

logger = logging.getLogger(__name__)


def register_routes(dp: Dispatcher) -> None:
    for reg in routes:
        reg(dp)


async def main() -> None:
    cfg = get_config()

    bot = Bot(token=cfg.bot.token)
    dp = Dispatcher()

    register_routes(dp)

    logger.info("Бот запускается...")

    try:
        await bot.delete_webhook()
    except Exception as exc:
        logger.warning("Ошибка удаления webhook: %s", exc)

    logger.info("Бот запущен и ожидает сообщений")
    await dp.start_polling(bot, skip_updates=cfg.bot.skip_updates_on_start)
