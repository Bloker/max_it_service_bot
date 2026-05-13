"""Сервис поиска комнаты и проживания гостя в Netarium."""

import logging
from re import fullmatch
from time import monotonic

from app.network.netarium.client import NetariumClient
from app.network.netarium.guest_parser import parse_guest_stays, parse_room_numbers
from app.network.netarium.models import NetariumGuestSearchResult, NetariumGuestStay
from config.config import NetariumConfig

logger = logging.getLogger(__name__)


class NetariumGuestService:
    """Проверяет существование комнаты и данные гостя в Netarium."""

    def __init__(
        self,
        cfg: NetariumConfig,
        client: NetariumClient | None = None,
    ) -> None:
        self.cfg = cfg
        self.client = client or NetariumClient(cfg)
        self._cached_stays: list[NetariumGuestStay] = []
        self._cached_rooms: set[str] = set()
        self._cache_loaded_at = 0.0

    async def find_by_room(self, raw_room: str) -> NetariumGuestSearchResult:
        room = raw_room.strip()
        if not fullmatch(r"\d{1,5}", room):
            return NetariumGuestSearchResult(
                ok=False,
                room=room,
                error=(
                    "Введите номер комнаты цифрами, например 2116."
                ),
            )

        if not self.cfg.is_configured:
            return NetariumGuestSearchResult(
                ok=False,
                room=room,
                error="Netarium API не настроен.",
            )

        try:
            stays, rooms = await self._get_data()
        except Exception:
            logger.exception("Netarium guest lookup failed")
            return NetariumGuestSearchResult(
                ok=False,
                room=room,
                error="Не удалось получить данные гостя из Netarium.",
            )

        # Наличие комнаты и наличие гостя разделены: номер может существовать
        # в дереве Netarium, но не иметь активной записи проживания.
        if room not in rooms:
            return NetariumGuestSearchResult(ok=True, room=room, room_exists=False)

        stay = next((item for item in stays if item.room == room), None)
        return NetariumGuestSearchResult(ok=True, room=room, stay=stay)

    async def _get_data(self) -> tuple[list[NetariumGuestStay], set[str]]:
        if self._is_cache_valid():
            return self._cached_stays, self._cached_rooms

        objects = await self.client.fetch_objects()
        self._cached_stays = parse_guest_stays(objects)
        self._cached_rooms = parse_room_numbers(objects)
        self._cache_loaded_at = monotonic()
        return self._cached_stays, self._cached_rooms

    def _is_cache_valid(self) -> bool:
        if self.cfg.cache_ttl_sec <= 0 or not self._cached_rooms:
            return False
        return monotonic() - self._cache_loaded_at <= self.cfg.cache_ttl_sec
