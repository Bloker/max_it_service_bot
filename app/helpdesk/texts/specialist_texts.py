from html import escape

from app.helpdesk.models.ticket import Ticket


def render_group_ticket(ticket: Ticket) -> str:
    assignee = escape(ticket.assignee_name or "не назначен")
    status = escape(ticket.status.value)
    category = escape(ticket.category)
    requester_name = escape(ticket.requester_name or "Пользователь")
    phone = escape(ticket.requester_phone or "не указан")
    text = escape(ticket.text)
    return (
        "🆘 Заявка IT Help Desk\n"
        f"ID: {escape(ticket.ticket_id)}\n"
        f"Статус: <b>{status}</b>\n"
        f"Исполнитель: <b>{assignee}</b>\n"
        f"Категория: {category}\n"
        f"Пользователь: {requester_name} (тел.: {phone})\n"
        "\nОписание:\n"
        f"{text}"
    )


ALREADY_ASSIGNED_TEXT = "Заявка уже назначена другому специалисту."
FORBIDDEN_TEXT = "Действие доступно только исполнителю или администратору."
NOT_FOUND_TEXT = "Заявка не найдена."
NOT_ASSIGNED_TEXT = "Заявка ещё не назначена."
ALREADY_CLOSED_TEXT = "Заявка уже закрыта."
