"""Сервис запуска сетевых диагностических инструментов."""

import logging
from datetime import datetime, timezone

from app.network.adapters.local_diagnostics_adapter import LocalDiagnosticsAdapter
from app.network.models.diagnostic import DiagnosticResult
from app.network.policy.corporate_policy import CorporateTargetPolicy
from app.network.policy.target_validator import normalize_target, validate_target_format
from app.network.services.templates_service import NetworkTemplatesService
from app.observability.services import ObservabilityService, truncate_for_observability
from config.config import NetworkToolsFeaturesConfig


logger = logging.getLogger(__name__)


class NetworkToolsService:
    """Единая точка запуска сетевых инструментов с проверкой политики."""

    def __init__(
        self,
        adapter: LocalDiagnosticsAdapter,
        policy: CorporateTargetPolicy,
        features: NetworkToolsFeaturesConfig,
        templates: NetworkTemplatesService,
        observability: ObservabilityService | None = None,
    ) -> None:
        self.adapter = adapter
        self.policy = policy
        self.features = features
        self.templates = templates
        self.observability = observability

    def _validate_target(self, raw_target: str) -> tuple[bool, str, str]:
        """Нормализует target и проверяет его по корпоративной политике."""

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
        """Запускает ping, если инструмент включен в конфиге."""

        if not self.features.ping:
            return DiagnosticResult(ok=False, title="Ping", details="Инструмент отключен в конфиге.")
        ok, reason, normalized = self._validate_target(target)
        if not ok:
            return DiagnosticResult(ok=False, title="Ping", details=reason)
        return await self.adapter.ping(normalized)

    async def dns_lookup(self, target: str) -> DiagnosticResult:
        """Запускает DNS lookup для разрешенного target."""

        if not self.features.dns_lookup:
            return DiagnosticResult(ok=False, title="DNS lookup", details="Инструмент отключен в конфиге.")
        ok, reason, normalized = self._validate_target(target)
        if not ok:
            return DiagnosticResult(ok=False, title="DNS lookup", details=reason)
        return await self.adapter.dns_lookup(normalized)

    async def host_check(self, target: str) -> DiagnosticResult:
        """Проверяет DNS и ping для разрешенного target."""

        if not self.features.host_check:
            return DiagnosticResult(ok=False, title="Host check", details="Инструмент отключен в конфиге.")
        ok, reason, normalized = self._validate_target(target)
        if not ok:
            return DiagnosticResult(ok=False, title="Host check", details=reason)
        return await self.adapter.host_check(normalized)

    async def traceroute(self, target: str) -> DiagnosticResult:
        """Запускает traceroute для разрешенного target."""

        if not self.features.traceroute:
            return DiagnosticResult(ok=False, title="Traceroute", details="Инструмент отключен в конфиге.")
        ok, reason, normalized = self._validate_target(target)
        if not ok:
            return DiagnosticResult(ok=False, title="Traceroute", details=reason)
        return await self.adapter.traceroute(normalized)

    async def nslookup(self, target: str) -> DiagnosticResult:
        """Запускает nslookup для разрешенного target."""

        if not self.features.nslookup:
            return DiagnosticResult(ok=False, title="NSLookup", details="Инструмент отключен в конфиге.")
        ok, reason, normalized = self._validate_target(target)
        if not ok:
            return DiagnosticResult(ok=False, title="NSLookup", details=reason)
        return await self.adapter.nslookup(normalized)

    async def whois(self, target: str) -> DiagnosticResult:
        """Запускает whois для разрешенного target."""

        if not self.features.whois:
            return DiagnosticResult(ok=False, title="Whois", details="Инструмент отключен в конфиге.")
        ok, reason, normalized = self._validate_target(target)
        if not ok:
            return DiagnosticResult(ok=False, title="Whois", details=reason)
        return await self.adapter.whois(normalized)

    def wifi_template(self) -> DiagnosticResult:
        """Возвращает текстовый шаблон диагностики Wi-Fi."""

        return DiagnosticResult(ok=True, title="Wi-Fi template", details=self.templates.wifi_troubleshooting())

    def device_template(self, device_type: str) -> DiagnosticResult:
        """Возвращает шаблон диагностики для типа устройства."""

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

    def _is_feature_enabled(self, tool: str) -> bool | None:
        """Возвращает состояние feature flag для инструмента."""

        mapping = {
            "ping": self.features.ping,
            "dns": self.features.dns_lookup,
            "host_check": self.features.host_check,
            "traceroute": self.features.traceroute,
            "nslookup": self.features.nslookup,
            "whois": self.features.whois,
        }
        return mapping.get(tool)

    async def run_tool(
        self,
        tool: str,
        target: str,
        *,
        actor_user_id: int | None = None,
        actor_name: str | None = None,
    ) -> DiagnosticResult:
        """Маршрутизирует текстовый код инструмента к конкретной диагностике."""

        logger.info("Network tool requested: tool=%s target=%s", tool, target)
        started_at = datetime.now(tz=timezone.utc)
        normalized_target = normalize_target(target)
        feature_enabled = self._is_feature_enabled(tool)
        if tool == "ping":
            result = await self.ping(target)
        elif tool == "dns":
            result = await self.dns_lookup(target)
        elif tool == "host_check":
            result = await self.host_check(target)
        elif tool == "traceroute":
            result = await self.traceroute(target)
        elif tool == "nslookup":
            result = await self.nslookup(target)
        elif tool == "whois":
            result = await self.whois(target)
        else:
            result = DiagnosticResult(ok=False, title="Network", details="Неизвестный инструмент.")
        await self._record_tool_run(
            tool=tool,
            target=target,
            normalized_target=normalized_target,
            feature_enabled=feature_enabled,
            result=result,
            started_at=started_at,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
        )
        return result

    async def _record_tool_run(
        self,
        *,
        tool: str,
        target: str,
        normalized_target: str,
        feature_enabled: bool | None,
        result: DiagnosticResult,
        started_at: datetime,
        actor_user_id: int | None,
        actor_name: str | None,
    ) -> None:
        """Пишет observability-запись сетевого инструмента."""

        if self.observability is None:
            return
        finished_at = datetime.now(tz=timezone.utc)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        output_excerpt, truncated = truncate_for_observability(result.details, limit=500)
        policy_decision = "allowed"
        status = "success" if result.ok else "failed"
        error_text = None
        if not result.ok:
            error_text = output_excerpt
            lowered = result.details.lower()
            if "запрещена политикой" in lowered:
                status = "denied"
                policy_decision = "denied"
            elif "timed out" in lowered or "timeout" in lowered:
                status = "timeout"
        if feature_enabled is False:
            policy_decision = "feature_disabled"
        await self.observability.network_tool_run(
            tool=tool,
            target=target,
            status=status,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
            normalized_target=normalized_target,
            policy_decision=policy_decision,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            output_excerpt=output_excerpt,
            output_truncated=truncated,
            error_text=error_text,
            feature_enabled=feature_enabled,
        )
        if status == "denied":
            await self.observability.audit(
                action="network_tool_denied_by_policy",
                resource_type="network_tool",
                resource_id=tool,
                result="denied",
                actor_user_id=actor_user_id,
                actor_role="IT specialist",
                reason="policy_denied",
                metadata={"target": normalized_target},
            )
