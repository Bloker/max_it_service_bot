"""Тексты истории заявок по номеру/домикам."""

from html import escape

from app.helpdesk.models.room_ticket_history import RoomTicketHistoryItem
from app.helpdesk.models.room_ticket_context import RoomTicketContext
from app.helpdesk.texts.formatters import (
    format_moscow_datetime_short,
    format_room_context_object,
)


def render_room_history(
    *,
    room_context: RoomTicketContext,
    items: list[RoomTicketHistoryItem],
) -> str:
    """Форматирует компактную историю заявок по объекту."""

    location_display = format_room_context_object(
        room_number_snapshot=room_context.room_number_snapshot,
        location_display_snapshot=room_context.location_display_snapshot,
    )
    lines = [
        "<b>История номера</b>",
        "",
        "Объект:",
        escape(location_display),
        "",
    ]
    if not items:
        lines.append("Других заявок по этому номеру не найдено.")
        return "\n".join(lines)

    count = len(items)
    lines.extend(
        [
            f"Последние {count} {_pluralize_tickets(count)}:",
            "",
        ]
    )
    for item in items:
        category = escape(item.category_snapshot or "Без категории")
        status = escape(item.status or "неизвестно")
        created_at = format_moscow_datetime_short(item.created_at)
        lines.append(
            f"<code>{escape(item.ticket_key)}</code> · {category} · {status} · {created_at}"
        )
    return "\n".join(lines)


def _pluralize_tickets(count: int) -> str:
    """Возвращает корректную форму слова 'заявка'."""

    remainder_100 = count % 100
    remainder_10 = count % 10
    if 11 <= remainder_100 <= 14:
        return "заявок"
    if remainder_10 == 1:
        return "заявка"
    if remainder_10 in {2, 3, 4}:
        return "заявки"
    return "заявок"
