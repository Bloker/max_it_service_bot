"""Уведомления пользователям о событиях по заявкам."""

import logging

from app.helpdesk.models.ticket import Ticket
from app.helpdesk.texts import user_texts

logger = logging.getLogger(__name__)


async def notify_user_ticket_closed(bot, ticket: Ticket) -> bool:
    """Отправляет автору заявки уведомление о выполнении."""

    try:
        await bot.send_message(
            user_id=ticket.user_id,
            text=user_texts.render_ticket_closed_notification(ticket),
        )
    except Exception:
        logger.exception(
            "Failed to notify user about closed ticket: ticket_id=%s user_id=%s",
            ticket.ticket_id,
            ticket.user_id,
        )
        return False
    return True
