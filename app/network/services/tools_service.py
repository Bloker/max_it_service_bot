import logging

from app.network.adapters.local_diagnostics_adapter import LocalDiagnosticsAdapter
from app.network.models.diagnostic import DiagnosticResult
from app.network.policy.corporate_policy import CorporateTargetPolicy
from app.network.policy.target_validator import normalize_target, validate_target_format
from app.network.services.templates_service import NetworkTemplatesService
from config.config import NetworkToolsFeaturesConfig


logger = logging.getLogger(__name__)


class NetworkToolsService:
    def __init__(
        self,
        adapter: LocalDiagnosticsAdapter,
        policy: CorporateTargetPolicy,
        features: NetworkToolsFeaturesConfig,
        templates: NetworkTemplatesService,
    ) -> None:
        self.adapter = adapter
        self.policy = policy
        self.features = features
        self.templates = templates

    def _validate_target(self, raw_target: str) -> tuple[bool, str, str]:
        target = normalize_target(raw_target)
        ok, error = validate_target_format(target)
        if not ok:
            logger.info("Network target format rejected: %s", target)
            return False, error, target

        allowed, reason = self.policy.is_allowed_target(target)
        if not allowed:
            logger.warning("Corporate policy rejected target '%s': %s", target, reason)
            return False, f"Проверка запрещена политикой: {reason}", target
        return True, "", target

    async def ping(self, target: str) -> DiagnosticResult:
        if not self.features.ping:
            return DiagnosticResult(ok=False, title="Ping", details="Инструмент отключен в конфиге.")
        ok, reason, normalized = self._validate_target(target)
        if not ok:
            return DiagnosticResult(ok=False, title="Ping", details=reason)
        return await self.adapter.ping(normalized)

    async def dns_lookup(self, target: str) -> DiagnosticResult:
        if not self.features.dns_lookup:
            return DiagnosticResult(ok=False, title="DNS lookup", details="Инструмент отключен в конфиге.")
        ok, reason, normalized = self._validate_target(target)
        if not ok:
            return DiagnosticResult(ok=False, title="DNS lookup", details=reason)
        return await self.adapter.dns_lookup(normalized)

    async def host_check(self, target: str) -> DiagnosticResult:
        if not self.features.host_check:
            return DiagnosticResult(ok=False, title="Host check", details="Инструмент отключен в конфиге.")
        ok, reason, normalized = self._validate_target(target)
        if not ok:
            return DiagnosticResult(ok=False, title="Host check", details=reason)
        return await self.adapter.host_check(normalized)

    async def traceroute(self, target: str) -> DiagnosticResult:
        if not self.features.traceroute:
            return DiagnosticResult(ok=False, title="Traceroute", details="Инструмент отключен в конфиге.")
        ok, reason, normalized = self._validate_target(target)
        if not ok:
            return DiagnosticResult(ok=False, title="Traceroute", details=reason)
        return await self.adapter.traceroute(normalized)

    async def nslookup(self, target: str) -> DiagnosticResult:
        if not self.features.nslookup:
            return DiagnosticResult(ok=False, title="NSLookup", details="Инструмент отключен в конфиге.")
        ok, reason, normalized = self._validate_target(target)
        if not ok:
            return DiagnosticResult(ok=False, title="NSLookup", details=reason)
        return await self.adapter.nslookup(normalized)

    async def whois(self, target: str) -> DiagnosticResult:
        if not self.features.whois:
            return DiagnosticResult(ok=False, title="Whois", details="Инструмент отключен в конфиге.")
        ok, reason, normalized = self._validate_target(target)
        if not ok:
            return DiagnosticResult(ok=False, title="Whois", details=reason)
        return await self.adapter.whois(normalized)

    def wifi_template(self) -> DiagnosticResult:
        return DiagnosticResult(ok=True, title="Wi-Fi template", details=self.templates.wifi_troubleshooting())

    def device_template(self, device_type: str) -> DiagnosticResult:
        if not self.policy.is_allowed_device_type(device_type):
            logger.info("Device template rejected by policy: %s", device_type)
            return DiagnosticResult(
                ok=False,
                title="Device template",
                details="Тип устройства не разрешён политикой.",
            )
        return DiagnosticResult(
            ok=True,
            title="Device template",
            details=self.templates.device_template(device_type),
        )

    async def run_tool(self, tool: str, target: str) -> DiagnosticResult:
        logger.info("Network tool requested: tool=%s target=%s", tool, target)
        if tool == "ping":
            return await self.ping(target)
        if tool == "dns":
            return await self.dns_lookup(target)
        if tool == "host_check":
            return await self.host_check(target)
        if tool == "traceroute":
            return await self.traceroute(target)
        if tool == "nslookup":
            return await self.nslookup(target)
        if tool == "whois":
            return await self.whois(target)
        return DiagnosticResult(ok=False, title="Network", details="Неизвестный инструмент.")
