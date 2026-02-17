from maxapi import Router
from maxapi.types import MessageCreated, Command


def register(dp, bot):
    @dp.message_created(Command("start"))
    async def cmd_start(event: MessageCreated):
        user = event.message.sender
        name = getattr(user, "first_name", None) or "друг"

        await event.message.answer(
            f"👋 Привет, {name}!\n\n"
            "Добро пожаловать! Я готов помочь."
        )

    @dp.message_created(Command("help"))
    async def cmd_help(event: MessageCreated):
        help_text = (
            "📋 **Доступные команды:**\n\n"
            "• /start — Запустить бота\n"
            "• /help — Показать эту справку\n"
            "• /info — Информация о боте\n\n"
            "Просто напишите мне сообщение, и я отвечу!"
        )
        await event.message.answer(help_text)