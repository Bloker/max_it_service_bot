"""Общие formatter-утилиты HelpDesk-текстов."""

from datetime import datetime
import re
from zoneinfo import ZoneInfo


_DIGITS_RE = re.compile(r"\D+")
_MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def format_ru_phone(phone: str | None) -> str:
    """Нормализует российский телефон для отображения в карточке."""

    if not phone:
        return "не указан"

    digits = _DIGITS_RE.sub("", str(phone))
    if len(digits) == 11 and digits.startswith("8"):
        return f"+7{digits[1:]}"
    if len(digits) == 11 and digits.startswith("7"):
        return f"+{digits}"
    if len(digits) == 10:
        return f"+7{digits}"
    return "не указан"


def format_room_context_object(
    *,
    room_number_snapshot: str | None,
    location_display_snapshot: str | None,
    category_snapshot: str | None = None,
) -> str:
    """Форматирует объект обслуживания в коротком виде."""

    location_display = location_display_snapshot or ""
    normalized_display = location_display.lower()
    if "домик" in normalized_display and room_number_snapshot:
        object_text = f"Домик {room_number_snapshot}"
    elif room_number_snapshot:
        object_text = f"Номер {room_number_snapshot}"
    elif location_display:
        object_text = location_display
    else:
        object_text = "не указан"
    if category_snapshot:
        object_text = f"{object_text} ({category_snapshot})"
    return object_text


def format_moscow_datetime_short(value: datetime) -> str:
    """Форматирует дату/время в часовом поясе Москвы."""

    if value.tzinfo is None:
        value = value.replace(tzinfo=_MOSCOW_TZ)
    return value.astimezone(_MOSCOW_TZ).strftime("%d.%m %H:%M")
