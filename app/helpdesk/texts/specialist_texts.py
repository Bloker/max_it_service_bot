"""Тексты и форматирование сообщений для IT-специалистов."""

from html import escape

from app.helpdesk.models.room_ticket_context import RoomTicketContext
from app.helpdesk.models.ticket import Ticket
from app.helpdesk.services.ticket_internal_comment_service import TicketInternalComment
from app.helpdesk.services.ticket_clarification_service import (
    TicketClarification,
    TicketClosingReply,
    TicketUserReply,
)
from app.helpdesk.texts.formatters import format_room_context_object, format_ru_phone


def _format_phone_link(phone: str | None) -> str:
    """Форматирует телефон как HTML tel-ссылку для карточки заявки."""

    formatted_phone = format_ru_phone(phone)
    if formatted_phone == "не указан":
        return formatted_phone
    return f'<a href="tel:{formatted_phone}">{formatted_phone}</a>'


def _format_room_context_line(room_context: RoomTicketContext) -> str:
    """Форматирует объект обслуживания одной строкой для карточки."""

    object_text = escape(
        format_room_context_object(
            room_number_snapshot=room_context.room_number_snapshot,
            location_display_snapshot=room_context.location_display_snapshot,
            category_snapshot=room_context.category_snapshot,
        )
    )
    return f"Объект: {object_text}"


def render_internal_comment_prompt(
    *,
    ticket_id: str,
    category_title: str | None,
    object_text: str | None,
) -> str:
    """Форматирует приглашение для внутреннего комментария специалиста."""

    lines = [f"Введите внутренний комментарий по заявке {escape(ticket_id)}.", ""]
    if object_text:
        lines.append(f"Объект: {escape(object_text)}")
    if category_title:
        lines.append(f"Категория: {escape(category_title)}")
    if object_text or category_title:
        lines.append("")
    lines.append("Комментарий не будет отправлен пользователю и не попадёт в базу знаний.")
    return "\n".join(lines)


def render_group_ticket(
    ticket: Ticket,
    *,
    room_context: RoomTicketContext | None = None,
    last_clarification: TicketClarification | None = None,
    attached_user_reply: TicketUserReply | None = None,
    closing_reply: TicketClosingReply | None = None,
    last_internal_comment: TicketInternalComment | None = None,
) -> str:
    """Форматирует карточку заявки для группового чата IT."""

    assignee = escape(ticket.assignee_name or "не назначен")
    status = escape(ticket.status.value)
    category = escape(ticket.category)
    requester_name = escape(ticket.requester_name or "Пользователь")
    phone = _format_phone_link(ticket.requester_phone)
    text = escape(ticket.text)
    object_or_category_line = (
        _format_room_context_line(room_context)
        if room_context is not None
        else f"Категория: {category}"
    )
    card_text = (
        "🆘 Заявка IT Help Desk\n"
        f"ID: {escape(ticket.ticket_id)}\n"
        f"Статус: <b>{status}</b>\n"
        f"Исполнитель: <b>{assignee}</b>\n"
        f"{object_or_category_line}\n"
        f"Пользователь: {requester_name}\n"
        f"Тел: {phone}\n"
        "\nОписание:\n"
        f"{text}"
    )
    blocks = [card_text]
    if last_clarification is not None:
        clarification_author = escape(last_clarification.actor_name)
        clarification_text = escape(last_clarification.card_text)
        blocks.append(
            "Последнее уточнение:\n"
            f"{clarification_author}: {clarification_text}"
        )
    if attached_user_reply is not None:
        reply_author = escape(attached_user_reply.user_name)
        reply_text = escape(attached_user_reply.card_text)
        blocks.append(
            "Ответ пользователя:\n"
            f"{reply_author}: {reply_text}"
        )
    if closing_reply is not None:
        blocks.append(
            "Ответ при закрытии:\n"
            f"{escape(closing_reply.card_text)}"
        )
    if last_internal_comment is not None:
        comment_text = escape(last_internal_comment.card_text)
        blocks.append(
            "Внутренний комментарий:\n"
            f"{comment_text}"
        )
    return "\n\n".join(blocks)


def render_open_tickets_list(tickets: list[Ticket], *, title: str = "Не закрытые заявки") -> str:
    """Форматирует список открытых заявок для специалистов."""

    if not tickets:
        return "Открытых заявок нет."

    lines = [
        f"<b>{escape(title)}</b>",
        f"Всего: <b>{len(tickets)}</b>",
        "",
    ]

    for index, ticket in enumerate(tickets, start=1):
        assignee = escape(ticket.assignee_name or "не назначен")
        status = escape(ticket.status.value)
        category = escape(ticket.category)
        ticket_id = escape(ticket.ticket_id)

        lines.extend(
            [
                f"<b>{index}. <code>{ticket_id}</code></b>",
                f"Статус: <b>{status}</b>",
                f"Исполнитель: {assignee}",
                f"Категория: {category}",
            ]
        )
        if index < len(tickets):
            lines.append("")

    return "\n".join(lines)


ALREADY_ASSIGNED_TEXT = "Заявка уже назначена другому специалисту."
FORBIDDEN_TEXT = "Действие доступно только исполнителю или администратору."
NOT_FOUND_TEXT = "Заявка не найдена."
NOT_ASSIGNED_TEXT = "Заявка ещё не назначена."
ALREADY_CLOSED_TEXT = "Заявка уже закрыта."
