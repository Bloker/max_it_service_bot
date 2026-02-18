import logging
from typing import Any

from maxapi.types import BotStarted, MessageCreated
from config.config import get_config

logger = logging.getLogger(__name__)


def register(dp) -> None:
    cfg = get_config()
    group_chat_id = cfg.bot.group_chat_id

    @dp.bot_started()
    async def handle_bot_started(event: BotStarted):
        user = event.user
        name = getattr(user, "first_name", None) or "друг"

        await event.bot.send_message(
            chat_id=event.chat_id,
            text=(
                f"👋 Привет, {name}!\n\n"
                "Напишите вашу проблему — я передам её в рабочий чат.\n"
                "Команды: /help"
            ),
        )

    @dp.message_created()
    async def forward_to_group(event: MessageCreated):
        if event.message.recipient.chat_type != "dialog":
            return

        sender = event.message.sender
        sender_id = sender.user_id
        full_name = (f"{sender.first_name} {sender.last_name}".strip() or sender.name or "Пользователь")

        text = event.message.body.text or ""
        if not text:
            text = "(без текста)"

        if text.startswith("/"):
            return

        # ✅ Вложения (как в твоих апдейтах: image/audio/video лежат в body.attachments)
        attachments = getattr(event.message.body, "attachments", None) or []

        group_text = (
            "🆘 Новое обращение\n"
            f"От: {full_name} (id: {sender_id})\n"
            "Текст:\n"
            f"{text}"
        )

        # ✅ Отправляем в группу уже с attachments — в чате они отобразятся “нормально”
        await event.bot.send_message(
            chat_id=group_chat_id,
            text=group_text,
            attachments=attachments,
        )

        await event.message.answer("✅ Принято! Я передал сообщение в рабочий чат.")


