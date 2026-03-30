from app.helpdesk.models.ticket import Ticket, TicketStatus


WELCOME_TEXT = (
    "Привет! Это IT Help Desk.\n"
    "Выберите действие в меню ниже."
)

HELP_TEXT = (
    "Я помогу передать обращение в IT-отдел.\n"
    "Шаги: категория -> описание -> подтверждение."
)

CATEGORY_PROMPT = "Выберите категорию обращения:"
PROBLEM_PROMPT = "Кратко опишите проблему одним сообщением."


def confirm_prompt(category: str, text: str) -> str:
    return (
        "Проверьте обращение перед отправкой:\n\n"
        f"Категория: {category}\n"
        f"Описание: {text}"
    )


SUBMITTED_TEXT = "Заявка принята и передана специалистам."
CANCELLED_TEXT = "Создание обращения отменено."


def user_ticket_line(ticket: Ticket) -> str:
    return f"{ticket.ticket_id} • {ticket.category} • {ticket.status.value}"


NO_TICKETS_TEXT = "У вас пока нет обращений."
MY_TICKETS_HEADER = "Ваши последние обращения:"


WIFI_HELP_TEXT = (
    "Wi-Fi и сеть:\n"
    "1) Проверьте подключение к корпоративной сети.\n"
    "2) Перезапустите адаптер Wi-Fi.\n"
    "3) Если не помогло — создайте обращение."
)


def status_human(status: TicketStatus) -> str:
    return status.value
