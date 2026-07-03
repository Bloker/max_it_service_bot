"""Пересылка медиа-сообщений MAX с безопасным fallback."""

import logging
from typing import Any

import aiohttp
from maxapi.enums.upload_type import UploadType
from maxapi.types import AttachmentPayload, AttachmentUpload, InputMediaBuffer

from app.helpdesk.services.attachment_filter_service import (
    get_attachment_token,
    get_attachment_url,
    is_audio_attachment,
    summarize_attachment,
)

logger = logging.getLogger(__name__)

AUDIO_DOWNLOAD_TIMEOUT_SEC = 20


class MediaForwardService:
    """Пересылает аудио/voice сначала native forward, затем fallback."""

    async def forward_audio_messages(
        self,
        *,
        bot: Any,
        source_messages: list[Any],
        ticket_id: str,
        user_id: int,
        target_chat_id: int | None = None,
        target_user_id: int | None = None,
    ) -> list[str]:
        """Пересылает все исходные audio-сообщения и возвращает id отправленных сообщений."""

        forwarded_message_ids: list[str] = []
        for source_message in source_messages:
            sent_mid = await self.forward_audio_with_fallback(
                bot=bot,
                source_message=source_message,
                ticket_id=ticket_id,
                user_id=user_id,
                target_chat_id=target_chat_id,
                target_user_id=target_user_id,
            )
            if sent_mid:
                forwarded_message_ids.append(sent_mid)
        return forwarded_message_ids

    async def forward_audio_with_fallback(
        self,
        *,
        bot: Any,
        source_message: Any,
        ticket_id: str,
        user_id: int,
        target_chat_id: int | None = None,
        target_user_id: int | None = None,
    ) -> str | None:
        """Переотправляет audio: сначала token, затем native forward, затем download."""

        source_mid = getattr(source_message, "message_id", None)
        attachments = list(getattr(source_message, "attachments", None) or [])
        target = _format_target(target_chat_id=target_chat_id, target_user_id=target_user_id)
        logger.info(
            "Audio detected: ticket_id=%s user_id=%s source_message_id=%s target=%s attachments=%s",
            ticket_id,
            user_id,
            source_mid,
            target,
            [summarize_attachment(attachment) for attachment in attachments],
        )

        sent_mid = await self.resend_audio_attachment(
            bot=bot,
            source_message=source_message,
            ticket_id=ticket_id,
            user_id=user_id,
            target_chat_id=target_chat_id,
            target_user_id=target_user_id,
        )
        if sent_mid:
            return sent_mid

        native_ok, native_mid = await self.forward_message_native(
            source_message=source_message,
            ticket_id=ticket_id,
            user_id=user_id,
            target_chat_id=target_chat_id,
            target_user_id=target_user_id,
        )
        if native_ok and native_mid:
            return native_mid

        logger.warning(
            "All audio forward methods failed: ticket_id=%s user_id=%s source_message_id=%s target=%s",
            ticket_id,
            user_id,
            source_mid,
            target,
        )
        await self._send_audio_failure_notice(
            bot=bot,
            ticket_id=ticket_id,
            target_chat_id=target_chat_id,
            target_user_id=target_user_id,
        )
        return None

    async def forward_message_native(
        self,
        *,
        source_message: Any,
        ticket_id: str,
        user_id: int,
        target_chat_id: int | None = None,
        target_user_id: int | None = None,
    ) -> tuple[bool, str | None]:
        """Пересылает оригинальное сообщение MAX через message.forward."""

        message = getattr(source_message, "message", None)
        source_mid = getattr(source_message, "message_id", None)
        if target_chat_id is None and target_user_id is None:
            logger.warning(
                "Audio native forward unavailable: empty target ticket_id=%s user_id=%s source_message_id=%s",
                ticket_id,
                user_id,
                source_mid,
            )
            return False, None
        if message is None or not hasattr(message, "forward"):
            logger.warning(
                "Audio native forward unavailable: ticket_id=%s user_id=%s source_message_id=%s",
                ticket_id,
                user_id,
                source_mid,
            )
            return False, None

        try:
            target = _format_target(
                target_chat_id=target_chat_id,
                target_user_id=target_user_id,
            )
            logger.info(
                "Audio native forward started: ticket_id=%s user_id=%s source_message_id=%s target=%s",
                ticket_id,
                user_id,
                source_mid,
                target,
            )
            forward_kwargs: dict[str, int] = {}
            if target_chat_id is not None:
                forward_kwargs["chat_id"] = target_chat_id
            if target_user_id is not None:
                forward_kwargs["user_id"] = target_user_id
            if target_chat_id is None:
                sent = await message.forward(chat_id=None, **forward_kwargs)
            else:
                sent = await message.forward(**forward_kwargs)
        except Exception:
            logger.warning(
                "Audio native forward failed: ticket_id=%s user_id=%s source_message_id=%s target=%s",
                ticket_id,
                user_id,
                source_mid,
                _format_target(target_chat_id=target_chat_id, target_user_id=target_user_id),
                exc_info=True,
            )
            return False, None

        sent_mid = _extract_message_id(sent)
        if not sent_mid:
            logger.warning(
                "Audio native forward returned empty message id: ticket_id=%s user_id=%s "
                "source_message_id=%s target=%s",
                ticket_id,
                user_id,
                source_mid,
                _format_target(target_chat_id=target_chat_id, target_user_id=target_user_id),
            )
            return False, None
        logger.info(
            "Audio message forwarded natively: ticket_id=%s user_id=%s source_message_id=%s "
            "target=%s forwarded_message_id=%s",
            ticket_id,
            user_id,
            source_mid,
            _format_target(target_chat_id=target_chat_id, target_user_id=target_user_id),
            sent_mid,
        )
        return True, sent_mid

    async def resend_audio_attachment(
        self,
        *,
        bot: Any,
        source_message: Any,
        ticket_id: str,
        user_id: int,
        target_chat_id: int | None = None,
        target_user_id: int | None = None,
    ) -> str | None:
        """Fallback: переотправляет audio через token, затем через download+upload."""

        source_mid = getattr(source_message, "message_id", None)
        if target_chat_id is None and target_user_id is None:
            logger.warning(
                "Audio fallback failed: empty target ticket_id=%s user_id=%s source_message_id=%s",
                ticket_id,
                user_id,
                source_mid,
            )
            return None
        attachment = self._find_audio_attachment(source_message)
        if attachment is None:
            logger.warning(
                "Audio fallback failed: no audio attachment ticket_id=%s user_id=%s source_message_id=%s",
                ticket_id,
                user_id,
                source_mid,
            )
            return None

        sent_mid = await self._resend_via_token(
            bot=bot,
            attachment=attachment,
            ticket_id=ticket_id,
            user_id=user_id,
            source_mid=source_mid,
            target_chat_id=target_chat_id,
            target_user_id=target_user_id,
        )
        if sent_mid:
            return sent_mid

        sent_mid = await self._resend_via_download(
            bot=bot,
            attachment=attachment,
            ticket_id=ticket_id,
            user_id=user_id,
            source_mid=source_mid,
            target_chat_id=target_chat_id,
            target_user_id=target_user_id,
        )
        if sent_mid:
            return sent_mid

        logger.info(
            "Audio resend via token and download both failed: ticket_id=%s user_id=%s source_message_id=%s",
            ticket_id,
            user_id,
            source_mid,
        )
        return None

    async def _resend_via_token(
        self,
        *,
        bot: Any,
        attachment: Any,
        ticket_id: str,
        user_id: int,
        source_mid: str | None,
        target_chat_id: int | None = None,
        target_user_id: int | None = None,
    ) -> str | None:
        """Переотправляет audio через upload token из исходного вложения."""

        token = get_attachment_token(attachment)
        if not token:
            logger.info(
                "Audio token resend skipped: no token ticket_id=%s user_id=%s source_message_id=%s",
                ticket_id,
                user_id,
                source_mid,
            )
            return None

        try:
            logger.info(
                "Audio token resend started: ticket_id=%s user_id=%s source_message_id=%s",
                ticket_id,
                user_id,
                source_mid,
            )
            send_kwargs: dict[str, Any] = {
                "text": f"Аудиосообщение к заявке {ticket_id}.",
                "attachments": [
                    AttachmentUpload(
                        type=UploadType.AUDIO,
                        payload=AttachmentPayload(token=token),
                    )
                ],
            }
            if target_chat_id is not None:
                send_kwargs["chat_id"] = target_chat_id
            if target_user_id is not None:
                send_kwargs["user_id"] = target_user_id
            sent = await bot.send_message(**send_kwargs)
        except Exception:
            logger.warning(
                "Audio token resend failed: ticket_id=%s user_id=%s source_message_id=%s target=%s",
                ticket_id,
                user_id,
                source_mid,
                _format_target(target_chat_id=target_chat_id, target_user_id=target_user_id),
                exc_info=True,
            )
            return None

        sent_mid = _extract_message_id(sent)
        logger.info(
            "Audio token resend success: ticket_id=%s user_id=%s source_message_id=%s "
            "target=%s forwarded_message_id=%s",
            ticket_id,
            user_id,
            source_mid,
            _format_target(target_chat_id=target_chat_id, target_user_id=target_user_id),
            sent_mid,
        )
        return sent_mid

    async def _resend_via_download(
        self,
        *,
        bot: Any,
        attachment: Any,
        ticket_id: str,
        user_id: int,
        source_mid: str | None,
        target_chat_id: int | None = None,
        target_user_id: int | None = None,
    ) -> str | None:
        """Fallback: скачивает audio по URL и отправляет как InputMediaBuffer."""

        url = get_attachment_url(attachment)
        if not url:
            logger.info(
                "Audio download resend skipped: no payload url ticket_id=%s user_id=%s source_message_id=%s",
                ticket_id,
                user_id,
                source_mid,
            )
            return None

        try:
            logger.info(
                "Audio fallback download started: ticket_id=%s user_id=%s source_message_id=%s",
                ticket_id,
                user_id,
                source_mid,
            )
            audio_bytes = await _download_attachment_bytes(url)
            logger.info(
                "Audio fallback upload started: ticket_id=%s user_id=%s source_message_id=%s bytes=%s",
                ticket_id,
                user_id,
                source_mid,
                len(audio_bytes),
            )
            send_kwargs: dict[str, Any] = {
                "text": f"Аудиосообщение к заявке {ticket_id}.",
                "attachments": [
                    InputMediaBuffer(
                        buffer=audio_bytes,
                        filename=f"{ticket_id}-audio.ogg",
                        type=UploadType.AUDIO,
                    )
                ],
            }
            if target_chat_id is not None:
                send_kwargs["chat_id"] = target_chat_id
            if target_user_id is not None:
                send_kwargs["user_id"] = target_user_id
            sent = await bot.send_message(**send_kwargs)
        except Exception:
            logger.warning(
                "Audio download resend failed: ticket_id=%s user_id=%s source_message_id=%s target=%s",
                ticket_id,
                user_id,
                source_mid,
                _format_target(target_chat_id=target_chat_id, target_user_id=target_user_id),
                exc_info=True,
            )
            return None

        sent_mid = _extract_message_id(sent)
        logger.info(
            "Audio download resend success: ticket_id=%s user_id=%s source_message_id=%s "
            "target=%s forwarded_message_id=%s",
            ticket_id,
            user_id,
            source_mid,
            _format_target(target_chat_id=target_chat_id, target_user_id=target_user_id),
            sent_mid,
        )
        return sent_mid

    def _find_audio_attachment(self, source_message: Any) -> Any | None:
        """Возвращает первое audio/voice-вложение исходного сообщения."""

        for attachment in list(getattr(source_message, "attachments", None) or []):
            if is_audio_attachment(attachment):
                return attachment
        return None

    async def _send_audio_failure_notice(
        self,
        *,
        bot: Any,
        ticket_id: str,
        target_chat_id: int | None = None,
        target_user_id: int | None = None,
    ) -> None:
        """Пишет безопасное уведомление без приватных media URL."""

        try:
            send_kwargs: dict[str, Any] = {
                "text": (
                    f"К заявке {ticket_id} пользователь приложил аудиосообщение, "
                    "но бот не смог переслать его автоматически. Проверьте логи."
                )
            }
            if target_chat_id is not None:
                send_kwargs["chat_id"] = target_chat_id
            if target_user_id is not None:
                send_kwargs["user_id"] = target_user_id
            await bot.send_message(**send_kwargs)
        except Exception:
            logger.warning(
                "Audio failure notice send failed: ticket_id=%s target=%s",
                ticket_id,
                _format_target(target_chat_id=target_chat_id, target_user_id=target_user_id),
                exc_info=True,
            )


async def _download_attachment_bytes(url: str) -> bytes:
    """Скачивает вложение по приватному URL, не раскрывая его в логах."""

    timeout = aiohttp.ClientTimeout(total=AUDIO_DOWNLOAD_TIMEOUT_SEC)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.read()


def _extract_message_id(sent_message: Any) -> str | None:
    """Достаёт MAX message_id из ответа отправки/пересылки."""

    body = getattr(getattr(sent_message, "message", None), "body", None)
    mid = getattr(body, "mid", None)
    return str(mid) if mid else None


def _format_target(
    *,
    target_chat_id: int | None,
    target_user_id: int | None,
) -> str:
    """Формирует безопасное описание адресата для логов."""

    if target_chat_id is not None:
        return f"chat:{target_chat_id}"
    if target_user_id is not None:
        return f"user:{target_user_id}"
    return "-"
