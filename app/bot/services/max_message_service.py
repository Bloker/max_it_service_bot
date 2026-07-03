"""Безопасные операции с сообщениями MAX."""

import logging
from typing import Any

from maxapi.enums.message_link_type import MessageLinkType
from maxapi.enums.parse_mode import ParseMode
from maxapi.types.message import NewMessageLink

from app.observability.services import ObservabilityService

logger = logging.getLogger(__name__)


class MaxMessageService:
    """Инкапсулирует update/send/answer операции MAX API."""

    def __init__(self, observability: ObservabilityService | None = None) -> None:
        self._observability = observability

    async def edit_message(
        self,
        *,
        bot,
        message_id: str,
        text: str,
        attachments: list[Any] | None = None,
        text_format: ParseMode | None = ParseMode.HTML,
        notify: bool = False,
    ) -> bool:
        """Редактирует сообщение бота."""

        try:
            await bot.edit_message(
                message_id=str(message_id),
                text=text,
                attachments=attachments,
                notify=notify,
                format=text_format,
            )
        except Exception:
            logger.exception("MAX edit_message failed: message_id=%s", message_id)
            await self._audit_max_message(
                action="max_message_edit_failed",
                resource_id=str(message_id),
                result="failed",
            )
            return False
        await self._audit_max_message(
            action="max_message_edit_success",
            resource_id=str(message_id),
            result="success",
        )
        return True

    async def send_message(
        self,
        *,
        bot,
        chat_id: int | None = None,
        user_id: int | None = None,
        text: str,
        attachments: list[Any] | None = None,
        reply_to_message_id: str | None = None,
        text_format: ParseMode | None = ParseMode.HTML,
        notify: bool = False,
    ) -> str | None:
        """Отправляет сообщение в чат или личный диалог пользователя."""

        link = None
        if reply_to_message_id:
            link = NewMessageLink(
                type=MessageLinkType.REPLY,
                mid=str(reply_to_message_id),
            )

        try:
            if chat_id is not None:
                sent = await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    attachments=attachments,
                    link=link,
                    notify=notify,
                    format=text_format,
                )
            else:
                sent = await bot.send_message(
                    user_id=user_id,
                    text=text,
                    attachments=attachments,
                    link=link,
                    notify=notify,
                    format=text_format,
                )
        except Exception:
            logger.exception(
                "MAX send_message failed: chat_id=%s user_id=%s",
                chat_id,
                user_id,
            )
            await self._audit_max_message(
                action="max_message_send_failed",
                resource_id=str(chat_id or user_id or "unknown"),
                result="failed",
                metadata={"target_type": "chat" if chat_id is not None else "user"},
            )
            return None

        message = getattr(sent, "message", None)
        body = getattr(message, "body", None)
        mid = getattr(body, "mid", None)
        message_id = str(mid) if mid else None
        await self._audit_max_message(
            action="max_message_sent",
            resource_id=message_id or str(chat_id or user_id or "unknown"),
            result="success" if message_id else "failed",
            metadata={"target_type": "chat" if chat_id is not None else "user"},
        )
        return message_id

    async def delete_message(self, *, bot, message_id: str | None) -> bool:
        """Удаляет сообщение, если известен его идентификатор."""

        if not message_id:
            return False
        try:
            await bot.delete_message(message_id=str(message_id))
        except Exception:
            logger.warning(
                "MAX delete_message failed: message_id=%s",
                message_id,
                exc_info=True,
            )
            await self._audit_max_message(
                action="max_message_delete_failed",
                resource_id=str(message_id),
                result="failed",
            )
            return False
        await self._audit_max_message(
            action="max_message_delete_success",
            resource_id=str(message_id),
            result="success",
        )
        return True

    async def answer_callback(self, *, event, notification: str) -> bool:
        """Отвечает на callback."""

        try:
            await event.answer(notification=notification)
        except Exception:
            logger.exception("MAX callback answer failed: notification=%s", notification)
            await self._audit_max_message(
                action="max_callback_answer_failed",
                resource_id="callback",
                result="failed",
            )
            return False
        await self._audit_max_message(
            action="max_callback_answer_success",
            resource_id="callback",
            result="success",
        )
        return True

    async def answer_callback_with_message(
        self,
        *,
        event,
        text: str,
        attachments: list[Any] | None = None,
        notification: str | None = None,
        text_format: ParseMode | None = ParseMode.HTML,
        notify: bool = False,
    ) -> bool:
        """Отвечает на callback с заменой текста и кнопок сообщения."""

        try:
            await event.answer(
                new_text=text,
                attachments=attachments or [],
                notification=notification,
                notify=notify,
                format=text_format,
            )
        except Exception:
            logger.exception("MAX callback message update failed")
            await self._audit_max_message(
                action="max_callback_answer_failed",
                resource_id="callback",
                result="failed",
                metadata={"with_message_update": True},
            )
            return False
        await self._audit_max_message(
            action="max_callback_answer_success",
            resource_id="callback",
            result="success",
            metadata={"with_message_update": True},
        )
        return True

    async def _audit_max_message(
        self,
        *,
        action: str,
        resource_id: str,
        result: str,
        metadata: dict | None = None,
    ) -> None:
        """Пишет audit MAX API операции без текста сообщений и вложений."""

        if self._observability is None:
            return
        await self._observability.audit(
            action=action,
            resource_type="max_message",
            resource_id=resource_id,
            result=result,
            metadata=metadata or {},
        )
