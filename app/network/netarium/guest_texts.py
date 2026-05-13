"""Форматирование карточки гостя из Netarium."""

from html import escape

from app.network.netarium.models import NetariumGuestSearchResult


def _format_dt(value) -> str:
    return value.strftime("%d.%m.%Y %H:%M")


def render_guest_search_result(result: NetariumGuestSearchResult) -> str:
    """Форматирует результат поиска гостя для MAX-сообщения."""

    room = escape(result.room or "-")
    if not result.ok:
        return f"<b>Гость: комната {room}</b>\n{escape(result.error)}"

    if not result.room_exists:
        return "Такого номера не существует"

    if result.stay is None:
        return (
            f"<b>Гость: комната {room}</b>\n"
            "Данные гостя не найдены."
        )

    return "\n".join(
        [
            f"<b>Гость: комната {room}</b>",
            f"Гость: <b>{escape(result.stay.guest_name)}</b>",
            f"Заезд: {_format_dt(result.stay.check_in)}",
            f"Выезд: {_format_dt(result.stay.check_out)}",
        ]
    )
