"""Сервис поиска WiFi-ваучеров по номеру комнаты."""

import logging
from re import fullmatch
from time import monotonic

from app.network.wifi.models import WifiVoucher, WifiVoucherSearchResult
from app.network.wifi.voucher_parser import parse_wifi_vouchers
from app.network.wifi.wifi_link_client import WifiLinkClient
from config.config import WifiLinkConfig

logger = logging.getLogger(__name__)


class WifiVoucherService:
    """Ищет актуальный WiFi-ваучер по номеру комнаты."""

    def __init__(
        self,
        cfg: WifiLinkConfig,
        client: WifiLinkClient | None = None,
    ) -> None:
        self.cfg = cfg
        self.client = client or WifiLinkClient(cfg)
        self._cached_vouchers: list[WifiVoucher] = []
        self._cache_loaded_at = 0.0
        self._cache_complete = False

    async def find_first_by_room(self, raw_room: str) -> WifiVoucherSearchResult:
        room = raw_room.strip()
        if not fullmatch(r"\d{1,5}", room):
            return WifiVoucherSearchResult(
                ok=False,
                room=room,
                error=(
                    "Введите номер комнаты цифрами, например 2116."
                ),
            )

        if not self.cfg.is_configured:
            return WifiVoucherSearchResult(
                ok=False,
                room=room,
                error=(
                    "WiFi-сервис не настроен: не заданы логин "
                    "или пароль кабинета."
                ),
            )

        try:
            vouchers = await self._get_vouchers(room=room)
        except Exception:
            logger.exception("WiFi voucher lookup failed")
            return WifiVoucherSearchResult(
                ok=False,
                room=room,
                error=(
                    "Не удалось получить данные из WiFi-кабинета. "
                    "Попробуйте позже."
                ),
            )

        matched = next((voucher for voucher in vouchers if voucher.room == room), None)
        if matched is None:
            return WifiVoucherSearchResult(
                ok=True,
                room=room,
                vouchers=(),
            )
        return WifiVoucherSearchResult(ok=True, room=room, vouchers=(matched,))

    async def _get_vouchers(self, *, room: str | None = None) -> list[WifiVoucher]:
        if self._is_cache_valid_for(room):
            return self._cached_vouchers

        pages: list[str]
        if room and hasattr(self.client, "fetch_voucher_pages_until"):
            # WiFi.link показывает ваучеры постранично; читаем страницы до первого
            # совпадения, чтобы не тянуть весь список без необходимости.
            pages = await self.client.fetch_voucher_pages_until(
                lambda html: any(
                    voucher.room == room for voucher in parse_wifi_vouchers(html)
                )
            )
        else:
            pages = await self.client.fetch_voucher_pages()

        vouchers: list[WifiVoucher] = []
        for page_html in pages:
            vouchers.extend(parse_wifi_vouchers(page_html))

        self._cached_vouchers = vouchers
        self._cache_loaded_at = monotonic()
        self._cache_complete = not room or len(pages) >= self.cfg.max_pages
        return vouchers

    def _is_cache_valid_for(self, room: str | None = None) -> bool:
        if self.cfg.cache_ttl_sec <= 0 or not self._cached_vouchers:
            return False
        if monotonic() - self._cache_loaded_at > self.cfg.cache_ttl_sec:
            return False
        if not room or self._cache_complete:
            return True
        # Частичный кеш нельзя использовать для другой комнаты: нужный ваучер
        # может находиться на более поздней странице.
        return any(voucher.room == room for voucher in self._cached_vouchers)
