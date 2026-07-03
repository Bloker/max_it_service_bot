import unittest

from app.network.models.diagnostic import DiagnosticResult
from app.network.policy.corporate_policy import CorporateTargetPolicy
from app.network.services.templates_service import NetworkTemplatesService
from app.network.services.tools_service import NetworkToolsService
from config.config import NetworkPolicyConfig, NetworkToolsFeaturesConfig
from tests.test_observability_service import FakeObservabilityRepository
from app.observability.services import ObservabilityService


class FakeDiagnosticsAdapter:
    async def ping(self, target: str) -> DiagnosticResult:
        return DiagnosticResult(ok=True, title="Ping", details=f"Хост: {target}")


class NetworkToolObservabilityTests(unittest.IsolatedAsyncioTestCase):
    def _service(self) -> tuple[NetworkToolsService, FakeObservabilityRepository]:
        repository = FakeObservabilityRepository()
        observability = ObservabilityService(repository=repository)
        policy = CorporateTargetPolicy(
            NetworkPolicyConfig(
                allowed_subnets=("10.0.0.0/8",),
                allowed_domain_suffixes=(".corp.local",),
                allowed_hosts=(),
                allowed_device_types=(),
            )
        )
        service = NetworkToolsService(
            adapter=FakeDiagnosticsAdapter(),
            policy=policy,
            features=NetworkToolsFeaturesConfig(
                ping=True,
                dns_lookup=True,
                host_check=True,
                traceroute=True,
                nslookup=True,
                whois=False,
            ),
            templates=NetworkTemplatesService(),
            observability=observability,
        )
        return service, repository

    async def test_successful_tool_run_is_recorded(self) -> None:
        service, repository = self._service()

        result = await service.run_tool("ping", "10.1.1.1", actor_user_id=501)

        self.assertTrue(result.ok)
        self.assertEqual(repository.network_runs[0].status, "success")
        self.assertEqual(repository.network_runs[0].actor_user_id, 501)

    async def test_policy_denied_tool_run_is_recorded(self) -> None:
        service, repository = self._service()

        result = await service.run_tool("ping", "8.8.8.8", actor_user_id=501)

        self.assertFalse(result.ok)
        self.assertEqual(repository.network_runs[0].status, "denied")
        self.assertEqual(repository.network_runs[0].policy_decision, "denied")
        self.assertEqual(repository.audit_records[0].action, "network_tool_denied_by_policy")


if __name__ == "__main__":
    unittest.main()
