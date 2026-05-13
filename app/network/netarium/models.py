"""Модели данных Netarium."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class NetariumGuestStay:
    """Данные проживания гостя в комнате."""

    room: str
    guest_name: str
    check_in: datetime
    check_out: datetime


@dataclass(frozen=True, slots=True)
class NetariumGuestSearchResult:
    """Результат проверки комнаты и гостя в Netarium."""

    ok: bool
    room: str
    stay: NetariumGuestStay | None = None
    room_exists: bool = True
    error: str = ""
