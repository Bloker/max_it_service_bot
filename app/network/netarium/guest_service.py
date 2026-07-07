"""Сервис поиска комнаты и проживания гостя в Netarium."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from re import fullmatch
from time import monotonic

from app.network.netarium.client import NetariumClient
from app.network.netarium.guest_parser import parse_guest_stays, parse_room_numbers
from app.network.netarium.models import NetariumGuestSearchResult, NetariumGuestStay
from app.observability.services import ObservabilityService
from config.config import NetariumConfig

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _NetariumLookupStats:
    """Внутренняя статистика Netarium без raw payload."""

    children_scanned: int = 0
    cache_hit: bool = False
    stays_loaded: int = 0
    rooms_loaded: int = 0


class NetariumGuestService:
    """Проверяет существование комнаты и данные гостя в Netarium."""

    def __init__(
        self,
        cfg: NetariumConfig,
        client: NetariumClient | None = None,
        observability: ObservabilityService | None = None,
    ) -> None:
        self.cfg = cfg
        self.client = client or NetariumClient(cfg)
        self.observability = observability
        self._cached_stays: list[NetariumGuestStay] = []
        self._cached_rooms: set[str] = set()
        self._cache_loaded_at = 0.0

    async def find_by_room(
        self,
        raw_room: str,
        *,
        actor_user_id: int | None = None,
        actor_name: str | None = None,
        chat_type: str | None = None,
        flow: str = "network_wifi",
    ) -> NetariumGuestSearchResult:
        """Проверяет комнату/гостя и пишет безопасный tool_run."""

        started_at = datetime.now(tz=timezone.utc)
        room = raw_room.strip()
        if not fullmatch(r"\d{1,5}", room):
            result = NetariumGuestSearchResult(
                ok=False,
                room=room,
                error=(
                    "Введите номер комнаты цифрами, например 2116."
                ),
            )
            await self._record_lookup(
                result=result,
                stats=_NetariumLookupStats(),
                started_at=started_at,
                actor_user_id=actor_user_id,
                actor_name=actor_name,
                chat_type=chat_type,
                flow=flow,
                status="validation_error",
                api_status="validation_error",
            )
            return result

        if not self.cfg.is_configured:
            result = NetariumGuestSearchResult(
                ok=False,
                room=room,
                error="Netarium API не настроен.",
            )
            await self._record_lookup(
                result=result,
                stats=_NetariumLookupStats(),
                started_at=started_at,
                actor_user_id=actor_user_id,
                actor_name=actor_name,
                chat_type=chat_type,
                flow=flow,
                status="external_error",
                api_status="not_configured",
            )
            return result

        try:
            stays, rooms, stats = await self._get_data()
        except Exception as exc:
            logger.warning(
                "Netarium guest lookup failed: room=%s error=%s",
                room,
                exc.__class__.__name__,
            )
            result = NetariumGuestSearchResult(
                ok=False,
                room=room,
                error="Не удалось получить данные гостя из Netarium.",
            )
            await self._record_lookup(
                result=result,
                stats=_NetariumLookupStats(),
                started_at=started_at,
                actor_user_id=actor_user_id,
                actor_name=actor_name,
                chat_type=chat_type,
                flow=flow,
                status=_external_error_status(exc),
                api_status=_external_error_status(exc),
            )
            return result

        # Наличие комнаты и наличие гостя разделены: номер может существовать
        # в дереве Netarium, но не иметь активной записи проживания.
        if room not in rooms:
            result = NetariumGuestSearchResult(ok=True, room=room, room_exists=False)
            await self._record_lookup(
                result=result,
                stats=stats,
                started_at=started_at,
                actor_user_id=actor_user_id,
                actor_name=actor_name,
                chat_type=chat_type,
                flow=flow,
                status="not_found",
                api_status="ok",
            )
            return result

        stay = next((item for item in stays if item.room == room), None)
        result = NetariumGuestSearchResult(ok=True, room=room, stay=stay)
        await self._record_lookup(
            result=result,
            stats=stats,
            started_at=started_at,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            chat_type=chat_type,
            flow=flow,
            status="success",
            api_status="ok",
        )
        return result

    async def _get_data(self) -> tuple[list[NetariumGuestStay], set[str], _NetariumLookupStats]:
        if self._is_cache_valid():
            return self._cached_stays, self._cached_rooms, _NetariumLookupStats(
                cache_hit=True,
                stays_loaded=len(self._cached_stays),
                rooms_loaded=len(self._cached_rooms),
            )

        objects = await self.client.fetch_objects()
        self._cached_stays = parse_guest_stays(objects)
        self._cached_rooms = parse_room_numbers(objects)
        self._cache_loaded_at = monotonic()
        return self._cached_stays, self._cached_rooms, _NetariumLookupStats(
            children_scanned=_count_objects(objects),
            cache_hit=False,
            stays_loaded=len(self._cached_stays),
            rooms_loaded=len(self._cached_rooms),
        )

    def _is_cache_valid(self) -> bool:
        if self.cfg.cache_ttl_sec <= 0 or not self._cached_rooms:
            return False
        return monotonic() - self._cache_loaded_at <= self.cfg.cache_ttl_sec

    async def _record_lookup(
        self,
        *,
        result: NetariumGuestSearchResult,
        stats: _NetariumLookupStats,
        started_at: datetime,
        actor_user_id: int | None,
        actor_name: str | None,
        chat_type: str | None,
        flow: str,
        status: str,
        api_status: str,
    ) -> None:
        """Пишет безопасный network.tool_runs для Netarium."""

        if self.observability is None:
            return
        finished_at = datetime.now(tz=timezone.utc)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        guest_found = result.stay is not None
        room_found = result.ok and result.room_exists
        metadata = {
            "room_found": room_found,
            "guest_found": guest_found,
            "object_class_matched": bool(self.cfg.object_class),
            "api_status": api_status,
            "children_scanned": stats.children_scanned,
            "cache_hit": stats.cache_hit,
            "stays_loaded": stats.stays_loaded,
            "rooms_loaded": stats.rooms_loaded,
            "has_start_end_dates": bool(
                result.stay and result.stay.check_in and result.stay.check_out
            ),
            "chat_type": chat_type,
            "flow": flow,
        }
        await self.observability.network_tool_run(
            tool="netarium_room_lookup",
            target=result.room,
            normalized_target=result.room,
            status=status,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            policy_decision="not_applicable",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            output_excerpt=_netarium_output_excerpt(status, result.room, room_found, guest_found),
            output_truncated=False,
            error_text=result.error or None if status in {"success", "not_found"} else result.error,
            feature_enabled=self.cfg.is_configured,
            metadata=metadata,
        )


def _count_objects(objects: list[dict]) -> int:
    count = 0
    stack = list(objects)
    while stack:
        item = stack.pop()
        count += 1
        children = item.get("children")
        if isinstance(children, list):
            stack.extend(child for child in children if isinstance(child, dict))
    return count


def _netarium_output_excerpt(status: str, room: str, room_found: bool, guest_found: bool) -> str:
    if status == "success":
        return f"Netarium room {room} found, guest_found={guest_found}"
    if status == "not_found" or not room_found:
        return f"Netarium room {room} not found"
    if status == "validation_error":
        return f"Netarium lookup validation error for room {room}"
    return f"Netarium lookup failed for room {room}"


def _external_error_status(exc: Exception) -> str:
    text = str(exc).lower()
    if isinstance(exc, TimeoutError) or "timeout" in text or "timed out" in text:
        return "timeout"
    if "http" in text:
        return "http_error"
    if "json" in text or "parse" in text or "unexpected" in text:
        return "parse_error"
    return "external_error"
