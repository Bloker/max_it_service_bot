"""Сервис поиска WiFi-ваучеров по номеру комнаты."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from re import fullmatch
from time import monotonic

from app.network.wifi.models import WifiVoucher, WifiVoucherSearchResult
from app.network.wifi.voucher_parser import parse_wifi_vouchers
from app.network.wifi.wifi_link_client import WifiLinkClient
from app.observability.services import ObservabilityService
from config.config import WifiLinkConfig

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _WifiLookupStats:
    """Внутренняя статистика поиска без приватных данных."""

    pages_scanned: int = 0
    cache_hit: bool = False
    cache_partial: bool = False
    cache_partial_continue: bool = False
    vouchers_loaded: int = 0


class WifiVoucherService:
    """Ищет актуальный WiFi-ваучер по номеру комнаты."""

    def __init__(
        self,
        cfg: WifiLinkConfig,
        client: WifiLinkClient | None = None,
        observability: ObservabilityService | None = None,
    ) -> None:
        self.cfg = cfg
        self.client = client or WifiLinkClient(cfg)
        self.observability = observability
        self._cached_vouchers: list[WifiVoucher] = []
        self._cache_loaded_at = 0.0
        self._cache_complete = False

    async def find_first_by_room(
        self,
        raw_room: str,
        *,
        actor_user_id: int | None = None,
        actor_name: str | None = None,
        chat_type: str | None = None,
        flow: str = "network_wifi",
        room_exists_in_netarium: bool | None = None,
        guest_found_in_netarium: bool | None = None,
    ) -> WifiVoucherSearchResult:
        """Ищет первый ваучер и пишет безопасный tool_run."""

        started_at = datetime.now(tz=timezone.utc)
        room = raw_room.strip()
        if not fullmatch(r"\d{1,5}", room):
            result = WifiVoucherSearchResult(
                ok=False,
                room=room,
                error=(
                    "Введите номер комнаты цифрами, например 2116."
                ),
            )
            await self._record_lookup(
                result=result,
                stats=_WifiLookupStats(),
                started_at=started_at,
                actor_user_id=actor_user_id,
                actor_name=actor_name,
                chat_type=chat_type,
                flow=flow,
                room_exists_in_netarium=room_exists_in_netarium,
                guest_found_in_netarium=guest_found_in_netarium,
                status="validation_error",
                external_status="validation_error",
            )
            return result

        if not self.cfg.is_configured:
            result = WifiVoucherSearchResult(
                ok=False,
                room=room,
                error=(
                    "WiFi-сервис не настроен: не заданы логин "
                    "или пароль кабинета."
                ),
            )
            await self._record_lookup(
                result=result,
                stats=_WifiLookupStats(),
                started_at=started_at,
                actor_user_id=actor_user_id,
                actor_name=actor_name,
                chat_type=chat_type,
                flow=flow,
                room_exists_in_netarium=room_exists_in_netarium,
                guest_found_in_netarium=guest_found_in_netarium,
                status="external_error",
                external_status="not_configured",
            )
            return result

        try:
            vouchers, stats = await self._get_vouchers(room=room)
        except Exception as exc:
            logger.warning(
                "WiFi voucher lookup failed: room=%s error=%s",
                room,
                exc.__class__.__name__,
            )
            result = WifiVoucherSearchResult(
                ok=False,
                room=room,
                error=(
                    "Не удалось получить данные из WiFi-кабинета. "
                    "Попробуйте позже."
                ),
            )
            await self._record_lookup(
                result=result,
                stats=_WifiLookupStats(),
                started_at=started_at,
                actor_user_id=actor_user_id,
                actor_name=actor_name,
                chat_type=chat_type,
                flow=flow,
                room_exists_in_netarium=room_exists_in_netarium,
                guest_found_in_netarium=guest_found_in_netarium,
                status=_external_error_status(exc),
                external_status=_external_error_status(exc),
            )
            return result

        matched = next((voucher for voucher in vouchers if voucher.room == room), None)
        if matched is None:
            result = WifiVoucherSearchResult(
                ok=True,
                room=room,
                vouchers=(),
            )
            await self._record_lookup(
                result=result,
                stats=stats,
                started_at=started_at,
                actor_user_id=actor_user_id,
                actor_name=actor_name,
                chat_type=chat_type,
                flow=flow,
                room_exists_in_netarium=room_exists_in_netarium,
                guest_found_in_netarium=guest_found_in_netarium,
                status="not_found",
                external_status="ok",
            )
            return result
        result = WifiVoucherSearchResult(ok=True, room=room, vouchers=(matched,))
        await self._record_lookup(
            result=result,
            stats=stats,
            started_at=started_at,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            chat_type=chat_type,
            flow=flow,
            room_exists_in_netarium=room_exists_in_netarium,
            guest_found_in_netarium=guest_found_in_netarium,
            status="success",
            external_status="ok",
        )
        return result

    async def _get_vouchers(self, *, room: str | None = None) -> tuple[list[WifiVoucher], _WifiLookupStats]:
        if self._is_cache_valid_for(room):
            return self._cached_vouchers, _WifiLookupStats(
                cache_hit=True,
                cache_partial=not self._cache_complete,
                vouchers_loaded=len(self._cached_vouchers),
            )

        pages: list[str]
        cache_partial_continue = bool(room and self._cached_vouchers and not self._cache_complete)
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
        return vouchers, _WifiLookupStats(
            pages_scanned=len(pages),
            cache_hit=False,
            cache_partial=not self._cache_complete,
            cache_partial_continue=cache_partial_continue,
            vouchers_loaded=len(vouchers),
        )

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

    async def _record_lookup(
        self,
        *,
        result: WifiVoucherSearchResult,
        stats: _WifiLookupStats,
        started_at: datetime,
        actor_user_id: int | None,
        actor_name: str | None,
        chat_type: str | None,
        flow: str,
        room_exists_in_netarium: bool | None,
        guest_found_in_netarium: bool | None,
        status: str,
        external_status: str,
    ) -> None:
        """Пишет безопасный network.tool_runs для WiFi.link."""

        if self.observability is None:
            return
        finished_at = datetime.now(tz=timezone.utc)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        voucher = result.vouchers[0] if result.vouchers else None
        output_excerpt = _wifi_output_excerpt(status, bool(voucher), result.room)
        metadata = {
            "room_exists_in_netarium": room_exists_in_netarium,
            "guest_found_in_netarium": guest_found_in_netarium,
            "voucher_found": voucher is not None,
            "pages_scanned": stats.pages_scanned,
            "cache_hit": stats.cache_hit,
            "cache_partial": stats.cache_partial,
            "cache_partial_continue": stats.cache_partial_continue,
            "external_status": external_status,
            "result_fields": _voucher_result_fields(voucher),
            "vouchers_loaded": stats.vouchers_loaded,
            "login_masked": _mask_voucher_login(voucher.login) if voucher else None,
            "chat_type": chat_type,
            "flow": flow,
        }
        await self.observability.network_tool_run(
            tool="wifi_voucher_lookup",
            target=result.room,
            normalized_target=result.room,
            status=status,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            policy_decision="not_applicable",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            output_excerpt=output_excerpt,
            output_truncated=False,
            error_text=result.error or None if status in {"success", "not_found"} else result.error,
            feature_enabled=self.cfg.is_configured,
            metadata=metadata,
        )


def _wifi_output_excerpt(status: str, voucher_found: bool, room: str) -> str:
    if status == "success" and voucher_found:
        return f"WiFi voucher found for room {room}"
    if status == "not_found":
        return f"WiFi voucher not found for room {room}"
    if status == "validation_error":
        return f"WiFi voucher lookup validation error for room {room}"
    return f"WiFi voucher lookup failed for room {room}"


def _voucher_result_fields(voucher: WifiVoucher | None) -> list[str]:
    if voucher is None:
        return []
    return [
        "login",
        "guest",
        "speed",
        "time_elapsed",
        "time_left",
        "downloaded",
        "valid_until",
        "created",
    ]


def _mask_voucher_login(login: str) -> str:
    parts = login.split(":")
    if len(parts) >= 3:
        return f"***:{parts[1]}:***"
    return "***"


def _external_error_status(exc: Exception) -> str:
    text = str(exc).lower()
    if isinstance(exc, TimeoutError) or "timeout" in text or "timed out" in text:
        return "timeout"
    if "authenticated" in text or "credentials" in text or "login" in text:
        return "auth_failed"
    if "parse" in text or "unexpected" in text:
        return "parse_error"
    return "external_error"
