import unittest
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from app.network.netarium.guest_parser import parse_guest_stays, parse_room_numbers
from app.network.netarium.models import NetariumGuestSearchResult
from app.network.netarium.guest_service import NetariumGuestService
from app.network.netarium.guest_texts import render_guest_search_result
from app.observability.services import ObservabilityService
from config.config import NetariumConfig
from tests.test_observability_service import FakeObservabilityRepository


_OBJECTS = [
    {
        "name": "1-й корпус",
        "children": [
            {
                "name": "1",
                "state": {
                    "start": 1778581575,
                    "end": 1778835600,
                    "guest": {"name": "НАДЕЖДА АКОПОВА"},
                },
                "children": [],
            },
            {
                "name": "1",
                "children": [
                    {
                        "name": "103",
                        "state": {
                            "start": 1778572920,
                            "end": 1778835600,
                            "guest": {"name": "АШОТ ОБАЯН"},
                        },
                        "children": [],
                    },
                    {
                        "name": "421",
                        "children": [],
                    },
                ],
            },
        ],
    }
]


class _FakeNetariumClient:
    def __init__(self, objects) -> None:
        self.objects = objects
        self.calls = 0

    async def fetch_objects(self):
        self.calls += 1
        return self.objects


class _FailingNetariumClient:
    async def fetch_objects(self):
        raise TimeoutError("request timeout")


def _netarium_config() -> NetariumConfig:
    return NetariumConfig(
        base_url="http://192.168.2.34:8081",
        api_key="999999",
        object_class="61746224-5eac-4663-a7db-396beffec01c",
        timeout_sec=10,
        cache_ttl_sec=120,
    )


class NetariumGuestTests(unittest.IsolatedAsyncioTestCase):
    def test_parse_guest_stays_recursively(self) -> None:
        stays = parse_guest_stays(_OBJECTS)

        self.assertEqual(len(stays), 2)
        self.assertEqual(stays[1].room, "103")
        self.assertEqual(stays[1].guest_name, "АШОТ ОБАЯН")
        self.assertEqual(stays[1].check_in, datetime(2026, 5, 12, 11, 2, tzinfo=ZoneInfo("Europe/Moscow")))
        self.assertEqual(stays[1].check_out, datetime(2026, 5, 15, 12, 0, tzinfo=ZoneInfo("Europe/Moscow")))

    def test_parse_room_numbers_includes_rooms_without_guest_state(self) -> None:
        rooms = parse_room_numbers(_OBJECTS)

        self.assertIn("103", rooms)
        self.assertIn("421", rooms)

    async def test_find_by_room_returns_guest_stay(self) -> None:
        client = _FakeNetariumClient(_OBJECTS)
        repository = FakeObservabilityRepository()
        service = NetariumGuestService(
            _netarium_config(),
            client=client,
            observability=ObservabilityService(repository=repository),
        )

        result = await service.find_by_room(
            "103",
            actor_user_id=1001,
            actor_name="Admin",
            chat_type="dialog",
        )

        self.assertTrue(result.ok)
        self.assertIsNotNone(result.stay)
        self.assertEqual(result.stay.guest_name, "АШОТ ОБАЯН")
        self.assertEqual(client.calls, 1)
        run = repository.network_runs[0]
        self.assertEqual(run.tool, "netarium_room_lookup")
        self.assertEqual(run.status, "success")
        self.assertEqual(run.actor_user_id, 1001)
        self.assertTrue(run.metadata["room_found"])
        self.assertTrue(run.metadata["guest_found"])
        self.assertTrue(run.metadata["has_start_end_dates"])
        serialized = json.dumps(run.metadata, ensure_ascii=False)
        self.assertNotIn("999999", serialized)
        self.assertNotIn("АШОТ", serialized)

    async def test_find_by_room_returns_existing_room_without_guest_stay(self) -> None:
        client = _FakeNetariumClient(_OBJECTS)
        repository = FakeObservabilityRepository()
        service = NetariumGuestService(
            _netarium_config(),
            client=client,
            observability=ObservabilityService(repository=repository),
        )

        result = await service.find_by_room("421")

        self.assertTrue(result.ok)
        self.assertTrue(result.room_exists)
        self.assertIsNone(result.stay)
        self.assertEqual(client.calls, 1)
        run = repository.network_runs[0]
        self.assertEqual(run.status, "success")
        self.assertTrue(run.metadata["room_found"])
        self.assertFalse(run.metadata["guest_found"])

    async def test_find_by_room_returns_empty_result_for_unknown_room(self) -> None:
        client = _FakeNetariumClient(_OBJECTS)
        repository = FakeObservabilityRepository()
        service = NetariumGuestService(
            _netarium_config(),
            client=client,
            observability=ObservabilityService(repository=repository),
        )

        result = await service.find_by_room("32323")

        self.assertTrue(result.ok)
        self.assertFalse(result.room_exists)
        self.assertIsNone(result.stay)
        self.assertEqual(client.calls, 1)
        run = repository.network_runs[0]
        self.assertEqual(run.status, "not_found")
        self.assertFalse(run.metadata["room_found"])

    async def test_observability_records_external_timeout(self) -> None:
        repository = FakeObservabilityRepository()
        service = NetariumGuestService(
            _netarium_config(),
            client=_FailingNetariumClient(),
            observability=ObservabilityService(repository=repository),
        )

        result = await service.find_by_room("103")

        self.assertFalse(result.ok)
        run = repository.network_runs[0]
        self.assertEqual(run.status, "timeout")
        self.assertEqual(run.metadata["api_status"], "timeout")

    def test_render_guest_search_result(self) -> None:
        stay = parse_guest_stays(_OBJECTS)[1]
        text = render_guest_search_result(NetariumGuestSearchResult(ok=True, room="103", stay=stay))

        self.assertIn("<b>Гость: комната 103</b>", text)
        self.assertIn("Гость: <b>АШОТ ОБАЯН</b>", text)
        self.assertIn("Заезд: 12.05.2026 11:02", text)
        self.assertIn("Выезд: 15.05.2026 12:00", text)

    def test_render_guest_search_result_for_unknown_room(self) -> None:
        text = render_guest_search_result(
            NetariumGuestSearchResult(ok=True, room="32323", room_exists=False)
        )

        self.assertEqual(text, "Такого номера не существует")


if __name__ == "__main__":
    unittest.main()
