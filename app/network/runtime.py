from app.network.adapters.command_runner import CommandRunner
from app.network.adapters.local_diagnostics_adapter import LocalDiagnosticsAdapter
from app.network.policy.corporate_policy import CorporateTargetPolicy
from app.network.services.session_service import NetworkSessionService
from app.network.services.templates_service import NetworkTemplatesService
from app.network.services.tools_service import NetworkToolsService
from config.config import get_config


_network_tools_service: NetworkToolsService | None = None
_network_session_service: NetworkSessionService | None = None


def get_network_tools_service() -> NetworkToolsService:
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
    )
    return _network_tools_service


def get_network_session_service() -> NetworkSessionService:
    global _network_session_service
    if _network_session_service is None:
        _network_session_service = NetworkSessionService()
    return _network_session_service

