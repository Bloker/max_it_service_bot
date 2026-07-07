"""Фабрики singleton-сервисов сетевых инструментов."""

from app.network.adapters.command_runner import CommandRunner
from app.network.adapters.local_diagnostics_adapter import LocalDiagnosticsAdapter
from app.network.policy.corporate_policy import CorporateTargetPolicy
from app.network.netarium.guest_service import NetariumGuestService
from app.network.services.session_service import NetworkSessionService
from app.network.services.templates_service import NetworkTemplatesService
from app.network.services.tools_service import NetworkToolsService
from app.network.wifi.voucher_service import WifiVoucherService
from app.observability.runtime import get_observability_service
from config.config import get_config


_network_tools_service: NetworkToolsService | None = None
_network_session_service: NetworkSessionService | None = None
_wifi_voucher_service: WifiVoucherService | None = None
_netarium_guest_service: NetariumGuestService | None = None


def get_network_tools_service() -> NetworkToolsService:
    """Создает singleton сервиса сетевых инструментов."""

    global _network_tools_service
    if _network_tools_service is not None:
        return _network_tools_service

    cfg = get_config()
    runner = CommandRunner(
        timeout_sec=cfg.network_tools.command_timeout_sec,
        max_output_chars=cfg.network_tools.max_output_chars,
    )
    adapter = LocalDiagnosticsAdapter(runner=runner)
    policy = CorporateTargetPolicy(cfg.network_tools.policy)
    templates = NetworkTemplatesService()
    _network_tools_service = NetworkToolsService(
        adapter=adapter,
        policy=policy,
        features=cfg.network_tools.features,
        templates=templates,
        observability=get_observability_service(),
    )
    return _network_tools_service


def get_network_session_service() -> NetworkSessionService:
    """Возвращает singleton in-memory сессий сетевых инструментов."""

    global _network_session_service
    if _network_session_service is None:
        _network_session_service = NetworkSessionService()
    return _network_session_service


def get_wifi_voucher_service() -> WifiVoucherService:
    """Возвращает singleton сервиса поиска WiFi-ваучеров."""

    global _wifi_voucher_service
    if _wifi_voucher_service is None:
        _wifi_voucher_service = WifiVoucherService(
            get_config().wifi_link,
            observability=get_observability_service(),
        )
    return _wifi_voucher_service


def get_netarium_guest_service() -> NetariumGuestService:
    """Возвращает singleton сервиса гостей Netarium."""

    global _netarium_guest_service
    if _netarium_guest_service is None:
        _netarium_guest_service = NetariumGuestService(
            get_config().netarium,
            observability=get_observability_service(),
        )
    return _netarium_guest_service
