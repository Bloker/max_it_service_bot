import logging
from maxapi.types import BotStarted, MessageCreated

logger = logging.getLogger(__name__)


def register(dp, bot):
    @dp.bot_started()
    async def handle_bot_started(message: BotStarted):
        user = message.user
        name = getattr(user, "first_name", None) or "друг"

        logger.info("Новый пользователь: %s (ID: %s)", name, user.user_id)

        await bot.send_message(
            chat_id=message.chat_id,
            text=(
                f"👋 Привет, {name}!\n\n"
                "Я ваш помощник. Чем могу помочь?\n\n"
                "Используйте /help для справки."
            ),
        )

    # (опционально) эхо на любые сообщения, кроме команд:
    @dp.message_created()
    async def echo_all(message: MessageCreated):
        await message.message.reply(message.message.body.text)