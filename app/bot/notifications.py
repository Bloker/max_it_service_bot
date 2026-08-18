"""Уведомления пользователям о событиях по заявкам."""

import logging
from typing import Any
from maxapi.enums.parse_mode import ParseMode

from app.bot.services.max_message_service import MaxMessageService
from app.helpdesk.models.room_ticket_context import RoomTicketContext
from app.helpdesk.models.ticket import Ticket
from app.helpdesk.keyboards.helpdesk_keyboards import (
    build_close_notification_menu_keyboard,
    build_user_ticket_keyboard,
)
from app.helpdesk.texts import user_texts

logger = logging.getLogger(__name__)


async def notify_user_ticket_submitted(
    *,
    bot,
    max_messages: MaxMessageService,
    ticket: Ticket,
    media_attachments: list[Any] | None = None,
    room_context: RoomTicketContext | None = None,
) -> str | None:
    """Показывает подтверждение и карточку заявки с действиями, без нового меню."""

    confirmation_mid = await max_messages.send_message(
        bot=bot,
        user_id=ticket.user_id,
        text=user_texts.SUBMITTED_TEXT,
        text_format=None,
    )
    card_mid = await max_messages.send_message(
        bot=bot,
        user_id=ticket.user_id,
        text=user_texts.render_user_ticket(ticket, room_context=room_context),
        attachments=[*(media_attachments or []), build_user_ticket_keyboard(ticket)],
        text_format=ParseMode.HTML,
    )
    return card_mid or confirmation_mid


async def notify_user_ticket_closed(bot, ticket: Ticket) -> bool:
    """Отправляет автору заявки уведомление о выполнении."""

    try:
        await bot.send_message(
            user_id=ticket.user_id,
            text=user_texts.render_ticket_closed_notification(ticket),
            attachments=[build_close_notification_menu_keyboard()],
        )
    except Exception:
        logger.exception(
            "Failed to notify user about closed ticket: ticket_id=%s user_id=%s",
            ticket.ticket_id,
            ticket.user_id,
        )
        return False
    return True
