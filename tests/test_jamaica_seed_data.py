import json
import os
import subprocess
import sys
import unittest
from collections import Counter
from pathlib import Path

from app.helpdesk.services.jamaica_seed_data import (
    JAMAICA_ISSUE_CATEGORIES,
    JAMAICA_KNOWLEDGE_SCOPES,
    build_jamaica_locations,
    normalize_room_number,
)
from app.helpdesk.services.location_service import LocationService


ROOT_DIR = Path(__file__).resolve().parents[1]


class JamaicaSeedDataTests(unittest.TestCase):
    def test_generates_253_unique_locations(self) -> None:
        locations = build_jamaica_locations()
        room_numbers = [location.room_number for location in locations]

        self.assertEqual(len(locations), 253)
        self.assertEqual(len(set(room_numbers)), 253)

    def test_counts_by_building(self) -> None:
        counts = Counter(
            (location.building_name, location.location_type)
            for location in build_jamaica_locations()
        )

        self.assertEqual(counts[("1 корпус", "room")], 100)
        self.assertEqual(counts[("2 корпус", "room")], 61)
        self.assertEqual(counts[("3 корпус", "room")], 62)
        self.assertEqual(counts[("Домики", "cottage")], 30)

    def test_sample_rooms_are_mapped_to_expected_buildings(self) -> None:
        by_room = {location.room_number: location for location in build_jamaica_locations()}

        self.assertEqual(by_room["101"].building_name, "1 корпус")
        self.assertEqual(by_room["2105"].building_name, "2 корпус")
        self.assertEqual(by_room["3101"].building_name, "3 корпус")
        self.assertEqual(by_room["15"].building_name, "Домики")
        self.assertEqual(by_room["15"].display_name, "Джамайка · Домик 15")

    def test_categories_are_in_expected_order(self) -> None:
        self.assertEqual(
            [(category.code, category.title) for category in JAMAICA_ISSUE_CATEGORIES],
            [
                ("tv", "ТВ"),
                ("telephony", "Телефония"),
                ("internet", "Интернет"),
                ("lock", "Замок"),
                ("other", "Прочее"),
            ],
        )

    def test_knowledge_scopes_are_production_catalog_only(self) -> None:
        self.assertEqual(
            [scope[0] for scope in JAMAICA_KNOWLEDGE_SCOPES],
            ["jamaica", "general_it", "infrastructure", "systems"],
        )

    def test_room_number_normalization_keeps_string_semantics(self) -> None:
        self.assertEqual(normalize_room_number("  101  А  "), "101 А")

    def test_seed_script_refuses_non_test_database_by_default(self) -> None:
        env = os.environ.copy()
        env.update(
            {
                "MAX_BOT_TOKEN": "test-token",
                "MAX_GROUP_CHAT_ID": "-100",
                "MAX_TICKET_BACKEND": "postgres",
                "MAX_TICKET_SCHEMA_MODE": "legacy",
                "MAX_TICKET_PG_HOST": "127.0.0.1",
                "MAX_TICKET_PG_PORT": "5432",
                "MAX_TICKET_PG_DB": "max_it_helpdesk_bot",
                "MAX_TICKET_PG_USER": "maxbot",
                "MAX_TICKET_PG_PASSWORD": "secret",
            }
        )

        result = subprocess.run(
            [sys.executable, "scripts/seed_jamaica_test_data.py"],
            cwd=ROOT_DIR,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing to seed non-test database", result.stderr)

    def test_seed_script_dry_run_json(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/seed_jamaica_test_data.py", "--dry-run-json"],
            cwd=ROOT_DIR,
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(result.stdout)

        self.assertEqual(payload["hotel_code"], "jamaica")
        self.assertEqual(len(payload["locations"]), 253)
        self.assertEqual(len(payload["categories"]), 5)

    def test_production_catalog_seed_refuses_without_explicit_flag(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/seed_jamaica_production_catalog.py"],
            cwd=ROOT_DIR,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing to write catalog data", result.stderr)

    def test_production_catalog_seed_dry_run_contains_no_ticket_or_kb_writes(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/seed_jamaica_production_catalog.py", "--dry-run-json"],
            cwd=ROOT_DIR,
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(result.stdout)

        self.assertEqual(len(payload["locations"]), 253)
        self.assertEqual(len(payload["categories"]), 5)
        self.assertEqual(len(payload["knowledge_scopes"]), 4)
        self.assertIn("helpdesk.knowledge_articles", payload["does_not_create"])
        self.assertIn("helpdesk.tickets", payload["does_not_create"])


class LocationServiceTests(unittest.TestCase):
    def test_service_normalizes_room_number_before_repository_lookup(self) -> None:
        repository = _FakeLocationRepository()
        service = LocationService(repository)

        service.find_location_by_room_number(10, "  2105  ")

        self.assertEqual(repository.last_lookup, (10, "2105"))


class _FakeLocationRepository:
    def __init__(self) -> None:
        self.last_lookup = None

    def find_hotel_by_code(self, code: str):
        return None

    def find_user_default_hotel(self, user_id: int):
        return None

    def find_location_by_room_number(self, hotel_id: int, room_number: str):
        self.last_lookup = (hotel_id, room_number)
        return None

    def list_issue_categories_for_hotel(self, hotel_id: int, *, requires_location=None):
        return ()


if __name__ == "__main__":
    unittest.main()
