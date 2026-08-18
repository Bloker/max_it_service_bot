"""Пользовательские тексты и форматирование сообщений HelpDesk."""

from html import escape

from app.helpdesk.models.room_ticket_context import RoomTicketContext
from app.helpdesk.models.ticket import Ticket, TicketStatus
from app.helpdesk.texts.formatters import format_room_context_object


WELCOME_TEXT = (
    "Меню IT Help Desk\n\n"
    "Выберите нужное действие в меню."
)

HELP_TEXT = (
    "Как пользоваться ботом:\n"
    "1) Выберите тип обращения в меню.\n"
    "2) Заполните данные, которые запросит бот.\n"
    "3) Опишите проблему (можно текст и фото).\n"
    "4) Через 20 секунд заявка отправится автоматически.\n"
    "- В случае если приходит обратное сообщение, отвечать на него"
    " необходимо ответом на сообщение."
)

ABOUT_TEXT = (
    "IT Help Desk Bot.\n"
    "Бот помогает быстро отправлять заявки в IT-отдел и отслеживать их статус."
)

CATEGORY_PROMPT = "Выберите категорию обращения:"
PROBLEM_PROMPT = (
    "Опишите проблему текстом. Можно отправить несколько сообщений и фото/файл.\n"
    "Через 20 секунд после последнего сообщения обращение отправится автоматически."
)

SUBMITTED_TEXT = "Заявка принята и передана специалистам."
CANCELLED_TEXT = "Создание обращения отменено."
MENU_CATEGORY_HINT_TEXT = "Выберите категорию в меню."


def user_ticket_line(ticket: Ticket) -> str:
    """Форматирует одну строку заявки в пользовательском списке."""

    return f"{ticket.ticket_id} • {ticket.category} • {ticket.status.value}"


def render_ticket_closed_notification(ticket: Ticket) -> str:
    """Форматирует уведомление пользователю о выполненной заявке."""

    return f"Заявка {ticket.ticket_id} выполнена."


def render_ticket_closed_with_reply_notification(ticket: Ticket, reply_text: str) -> str:
    """Форматирует уведомление о закрытии заявки с ответом специалиста."""

    return (
        f"Заявка {ticket.ticket_id} выполнена.\n\n"
        "Ответ специалиста:\n"
        f"{reply_text}"
    )


NO_TICKETS_TEXT = "У вас пока нет обращений."
MY_TICKETS_HEADER = "Ваши последние обращения:"


WIFI_SCOPE_TEXT = (
    "Внимание! Если проблема возникает на одном устройстве, а у остальных всё работает, "
    "это чаще всего связано с настройками устройства (VPN, родительский контроль, "
    "привязка к корпоративной сети и т.д.).\n"
    "Сотрудники IT не имеют права брать в руки устройство гостя, но всегда помогут "
    "с рекомендациями по подключению.\n\n"
    "Уточните, у какого количества гостей проблема:"
)

WIFI_DEVICE_PROMPT_TEXT = "Выберите тип устройства гостя:"

WIFI_MOBILE_RECOMMENDATIONS_TEXT = (
    "Рекомендации для гостя по подключению к Wi-Fi:\n"
    "1) Отключите VPN на устройстве.\n"
    "2) Отключитесь от Wi-Fi и забудьте сеть.\n"
    "3) Подключитесь к сети Wi-Fi заново.\n\n"
    "Должна появиться страница авторизации.\n"
    "Страница авторизации появляется?"
)

WIFI_LAPTOP_RECOMMENDATIONS_TEXT = (
    "Рекомендации для гостя по подключению к Wi-Fi:\n"
    "1) Отключите VPN на устройстве.\n"
    "2) Отключитесь от Wi-Fi и забудьте сеть.\n"
    "3) Подключитесь к сети Wi-Fi заново.\n"
    "4) Если в браузере есть блокировщики рекламы/расширения, временно отключите их.\n"
    "5) Очистите cookies и кэш, попробуйте другой браузер или режим инкогнито.\n\n"
    "Страница авторизации появляется?"
)

WIFI_SURNAME_CHECK_TEXT = (
    "Проверьте правильность ввода фамилии и сверьтесь, как гость заведен в системе.\n"
    "Нет ли опечатки в фамилии"
)

WIFI_ESCALATE_TEXT = (
    "Нужно передать заявку в чат поддержки.\n"
    "Отправьте в чат: номер, фамилию, контактный телефон, "
    "скриншот/фото ошибки (по возможности)."
)

TV_ESCALATE_TEXT = (
    "Нужно передать заявку в чат поддержки по ТВ.\n"
    "Отправьте в чат: номер комнаты, описание проблемы, контактный телефон, "
    "фото/видео (по возможности)."
)

WIFI_RESOLVED_TEXT = "Отлично, проблема решена."


def status_human(status: TicketStatus) -> str:
    """Возвращает человекочитаемый статус заявки."""

    return status.value


def render_user_ticket(
    ticket: Ticket,
    *,
    room_context: RoomTicketContext | None = None,
    last_user_addition=None,
) -> str:
    """Форматирует карточку собственной заявки пользователя."""

    context_line = f"Категория: {escape(ticket.category)}"
    if room_context is not None:
        context_line = "Объект: " + escape(
            format_room_context_object(
                room_number_snapshot=room_context.room_number_snapshot,
                location_display_snapshot=room_context.location_display_snapshot,
                category_snapshot=room_context.category_snapshot or ticket.category,
            )
        )
    card = (
        f"<b>Заявка {escape(ticket.ticket_id)}</b>\n"
        f"Статус: <b>{escape(ticket.status.value)}</b>\n"
        f"{context_line}\n\n"
        "<b>Описание:</b>\n"
        f"{escape(ticket.text)}"
    )
    if last_user_addition is not None:
        card += (
            "\n\n<b>Последнее дополнение:</b>\n"
            f"{escape(last_user_addition.card_text)}"
        )
    return card
