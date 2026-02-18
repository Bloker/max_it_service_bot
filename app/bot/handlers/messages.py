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

    def _find_chat_id(obj: Any) -> int | None:
        """
        Рекурсивно ищет chat_id/peer_id/etc в event.data.
        Работает с dict/list и объектами (через __dict__).
        """
        wanted_keys = {"chat_id", "peer_id", "conversation_id", "chatId", "peerId", "conversation_message_id"}

        def walk(x: Any) -> int | None:
            if x is None:
                return None

            # dict
            if isinstance(x, dict):
                for k, v in x.items():
                    if isinstance(k, str) and k in wanted_keys and isinstance(v, int):
                        return v
                for v in x.values():
                    found = walk(v)
                    if found is not None:
                        return found
                return None

            # list/tuple
            if isinstance(x, (list, tuple)):
                for item in x:
                    found = walk(item)
                    if found is not None:
                        return found
                return None

            # объект
            d = getattr(x, "__dict__", None)
            if isinstance(d, dict):
                return walk(d)

            return None

        return walk(obj)


    @dp.message_created()
    async def forward_to_group(event: MessageCreated):
        sender = event.message.sender
        sender_id = getattr(sender, "user_id", None)

        # 1) Пытаемся определить исходный chat_id


        src_chat_id = (
            getattr(event, "chat_id", None)
            or getattr(event.message, "chat_id", None)
            or getattr(event.message, "peer_id", None)
            or getattr(event.message.recipient, "chat_id", None)
            or getattr(event.message.recipient, "peer_id", None)
        )

        # print(f'src_chat_id = {src_chat_id}')


        # 2) Если не нашли — ищем в event.data (у тебя там точно лежит chat_id, судя по логу dispatcher)
        if src_chat_id is None:
            src_chat_id = _find_chat_id(getattr(event, "data", None))

        src_chat_id_str = str(src_chat_id) if src_chat_id is not None else None
        group_chat_id_str = str(group_chat_id)

        # print(f'src_chat_id_str= {src_chat_id_str}')
        # print(f'type src_chat_id_str= {type(src_chat_id_str)}')
        # print(f'group_chat_id_str= {group_chat_id_str}')
        # print(f'type group_chat_id_str= {type(group_chat_id_str)}')

        logger.info(
            "SRC chat_id=%s (%s) group_chat_id=%s (%s) sender_id=%s",
            src_chat_id, type(src_chat_id).__name__,
            group_chat_id, type(group_chat_id).__name__,
            sender_id
        )

        # 3) Антипетля: если это сообщение из группы — не пересылаем
        if src_chat_id_str == group_chat_id_str:
            logger.info("Сообщение из группы - игнорируем")
            return

        if hasattr(event.message, 'conversation_message_id'):
            logger.info("Обнаружено групповое сообщение по conversation_message_id - игнорируем")
            return

        # 4) Текст
        text = getattr(getattr(event.message, "body", None), "text", None) or ""
        if not text:
            text = "(без текста)"

        # 5) Не пересылаем команды
        if text.startswith("/"):
            return

        first_name = getattr(sender, "first_name", "") or ""
        last_name = getattr(sender, "last_name", "") or ""
        full_name = (first_name + " " + last_name).strip() or "Пользователь"

        group_text = (
            "🆘 Новое обращение\n"
            f"От: {full_name} (id: {sender_id})\n"
            "Текст:\n"
            f"{text}"
        )

        # 6) Пересылаем в группу и подтверждаем пользователю
        await event.bot.send_message(chat_id=group_chat_id, text=group_text)
        await event.message.answer("✅ Принято! Я передал сообщение в рабочий чат.")
