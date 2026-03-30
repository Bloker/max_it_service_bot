from app.helpdesk.models.ticket import Ticket


def render_group_ticket(ticket: Ticket) -> str:
    assignee = ticket.assignee_name or "не назначен"
    phone = ticket.requester_phone or "-"
    department = ticket.requester_department or "-"
    return (
        "🆘 Заявка IT Help Desk\n"
        f"ID: {ticket.ticket_id}\n"
        f"Статус: {ticket.status.value}\n"
        f"Исполнитель: {assignee}\n"
        f"Категория: {ticket.category}\n"
        f"Пользователь: {ticket.requester_name} (id: {ticket.requester_user_id})\n"
        f"Телефон: {phone}\n"
        f"Подразделение: {department}\n"
        "Описание:\n"
        f"{ticket.text}"
    )


ALREADY_ASSIGNED_TEXT = "Заявка уже назначена другому специалисту."
FORBIDDEN_TEXT = "Действие доступно только исполнителю или администратору."
NOT_FOUND_TEXT = "Заявка не найдена."
NOT_ASSIGNED_TEXT = "Заявка ещё не назначена."
ALREADY_CLOSED_TEXT = "Заявка уже закрыта."
