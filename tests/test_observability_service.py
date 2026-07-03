import unittest

from app.observability.models import AuditRecord, NetworkToolRunRecord, TicketEventRecord
from app.observability.services import ObservabilityService, truncate_for_observability


class FakeObservabilityRepository:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.ticket_events: list[TicketEventRecord] = []
        self.audit_records: list[AuditRecord] = []
        self.network_runs: list[NetworkToolRunRecord] = []

    def record_ticket_event(self, record: TicketEventRecord) -> None:
        if self.fail:
            raise RuntimeError("db down")
        self.ticket_events.append(record)

    def record_audit(self, record: AuditRecord) -> None:
        if self.fail:
            raise RuntimeError("db down")
        self.audit_records.append(record)

    def record_network_tool_run(self, record: NetworkToolRunRecord) -> None:
        if self.fail:
            raise RuntimeError("db down")
        self.network_runs.append(record)


class ObservabilityServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_records_ticket_event_audit_and_network_run(self) -> None:
        repository = FakeObservabilityRepository()
        service = ObservabilityService(repository=repository)

        await service.ticket_event(
            ticket_id="T-00001",
            event_type="ticket_created",
            actor_user_id=101,
            metadata={"category": "VPN"},
        )
        await service.audit(
            action="access_denied",
            resource_type="ticket",
            resource_id="T-00001",
            result="denied",
            actor_user_id=102,
            reason="forbidden",
        )
        await service.network_tool_run(
            tool="ping",
            target="10.0.0.1",
            status="success",
            actor_user_id=501,
        )

        self.assertEqual(repository.ticket_events[0].event_type, "ticket_created")
        self.assertEqual(repository.audit_records[0].result, "denied")
        self.assertEqual(repository.network_runs[0].tool, "ping")

    async def test_repository_errors_do_not_escape(self) -> None:
        service = ObservabilityService(repository=FakeObservabilityRepository(fail=True))

        await service.ticket_event(ticket_id="T-00001", event_type="ticket_created")
        await service.audit(
            action="x",
            resource_type="ticket",
            resource_id="T-00001",
            result="failed",
        )
        await service.network_tool_run(tool="ping", target="10.0.0.1", status="failed")

    async def test_feature_flags_disable_writes(self) -> None:
        repository = FakeObservabilityRepository()
        service = ObservabilityService(
            repository=repository,
            audit_enabled=False,
            ticket_events_enabled=False,
            network_tool_runs_enabled=False,
        )

        await service.ticket_event(ticket_id="T-00001", event_type="ticket_created")
        await service.audit(action="x", resource_type="ticket", resource_id="T-00001", result="success")
        await service.network_tool_run(tool="ping", target="10.0.0.1", status="success")

        self.assertEqual(repository.ticket_events, [])
        self.assertEqual(repository.audit_records, [])
        self.assertEqual(repository.network_runs, [])

    def test_truncate_for_observability(self) -> None:
        text, truncated = truncate_for_observability("abcdef", limit=3)

        self.assertEqual(text, "abc...")
        self.assertTrue(truncated)


if __name__ == "__main__":
    unittest.main()
