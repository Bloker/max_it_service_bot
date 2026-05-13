"""Модели WiFi-ваучеров."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class WifiVoucher:
    """Безопасное представление ваучера без пароля и остатка трафика."""

    login: str
    room: str
    guest: str
    speed_mbps: str
    elapsed_hours: str
    remaining_hours: str
    downloaded_mb: str
    validity: str
    created_date: date
    created_raw: str


@dataclass(frozen=True, slots=True)
class WifiVoucherSearchResult:
    """Результат поиска ваучера по номеру комнаты."""

    ok: bool
    room: str
    vouchers: tuple[WifiVoucher, ...] = ()
    error: str = ""
