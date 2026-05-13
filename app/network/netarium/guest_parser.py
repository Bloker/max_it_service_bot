"""Парсинг дерева объектов Netarium."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.network.netarium.models import NetariumGuestStay

_MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def _timestamp_to_moscow(value) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=_MOSCOW_TZ)
    except (TypeError, ValueError, OSError):
        return None


def parse_guest_stays(objects: list[dict]) -> list[NetariumGuestStay]:
    """Извлекает проживание гостя из дерева объектов Netarium."""

    stays: list[NetariumGuestStay] = []

    def walk(items) -> None:
        for item in items or []:
            if not isinstance(item, dict):
                continue

            state = item.get("state")
            if isinstance(state, dict):
                guest = state.get("guest")
                guest_name = ""
                if isinstance(guest, dict):
                    guest_name = str(guest.get("name") or "").strip()

                room = str(item.get("name") or "").strip()
                check_in = _timestamp_to_moscow(state.get("start"))
                check_out = _timestamp_to_moscow(state.get("end"))

                if room and guest_name and check_in and check_out:
                    stays.append(
                        NetariumGuestStay(
                            room=room,
                            guest_name=guest_name,
                            check_in=check_in,
                            check_out=check_out,
                        )
                    )

            walk(item.get("children") or [])

    walk(objects)
    return stays


def parse_room_numbers(objects: list[dict]) -> set[str]:
    """Возвращает все номера комнат, даже если по ним нет гостевой записи."""

    rooms: set[str] = set()

    def walk(items) -> None:
        for item in items or []:
            if not isinstance(item, dict):
                continue

            children = item.get("children") or []
            room = str(item.get("name") or "").strip()
            state = item.get("state")
            # В Netarium корпус/этаж тоже могут называться цифрами. Номер
            # комнаты отличаем по state или по отсутствию дочерних объектов.
            if room.isdigit() and (isinstance(state, dict) or not children):
                rooms.add(room)

            walk(children)

    walk(objects)
    return rooms
