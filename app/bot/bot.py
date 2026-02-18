import logging

from maxapi import Bot, Dispatcher

from config.config import get_config
from app.bot.handlers import routes

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
    except Exception as e:
        logger.warning("Ошибка удаления webhook: %s", e)

    logger.info("Бот запущен и ожидает сообщений")
    await dp.start_polling(bot)