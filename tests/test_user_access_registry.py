import tempfile
import unittest
from pathlib import Path

from app.admin.services.user_access_registry import UserAccessRegistry


class UserAccessRegistryTests(unittest.TestCase):
    def test_request_and_approve_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            registry = UserAccessRegistry(str(path))

            self.assertEqual(registry.request_access(1001, "Test User"), "created")
            self.assertEqual(registry.request_access(1001, "Test User"), "already_pending")

            pending = registry.list_pending()
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0].user_id, 1001)

            self.assertEqual(registry.approve(1001, role="it"), "approved")
            self.assertTrue(registry.is_approved(1001))
            self.assertEqual(registry.approve(1001), "already_approved")
            self.assertEqual(registry.get_ids_by_role("IT specialist"), (1001,))

    def test_reject_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            registry = UserAccessRegistry(str(path))

            self.assertEqual(registry.request_access(2002, "Reject User", phone="+70000000000"), "created")
            self.assertEqual(registry.reject(2002), "rejected")
            self.assertEqual(registry.reject(2002), "not_found")

    def test_ban_and_delete_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            registry = UserAccessRegistry(str(path))

            self.assertEqual(registry.request_access(3003, "Ban User", phone="+79990001122"), "created")
            self.assertEqual(registry.approve(3003, role="user"), "approved")
            self.assertEqual(registry.ban(3003), "banned")
            self.assertEqual(registry.ban(3003), "already_banned")
            self.assertIn(3003, registry.get_banned_ids())
            self.assertEqual(registry.delete_user(3003), "deleted")
            self.assertEqual(registry.delete_user(3003), "not_found")

    def test_invalid_role_on_approve(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            registry = UserAccessRegistry(str(path))

            self.assertEqual(registry.request_access(4004, "Role User", phone="+70000000004"), "created")
            self.assertEqual(registry.approve(4004, role="unknown"), "invalid_role")

    def test_hotel_assignment_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            registry = UserAccessRegistry(str(path))

            self.assertEqual(registry.request_access(5005, "Hotel User", phone="+70000000005"), "created")
            self.assertEqual(registry.approve(5005, role="user"), "approved")

            self.assertIsNone(registry.get_user_hotel(5005))
            self.assertEqual(registry.set_user_hotel(5005, "unknown"), "invalid_hotel")
            self.assertEqual(registry.set_user_hotel(5005, "jamaica"), "updated")
            self.assertEqual(registry.get_user_hotel(5005), "jamaica")
            self.assertEqual(registry.get_hotel_label("jamaica"), "Отель Джамайка")
            self.assertEqual(
                registry.get_hotel_features("jamaica"),
                ("wifi_guest_issue", "tv_guest_issue"),
            )
            self.assertEqual(registry.set_user_hotel(5005, "jamaica"), "no_change")
            self.assertEqual(registry.set_user_hotel(5005, "none"), "updated")
            self.assertIsNone(registry.get_user_hotel(5005))


if __name__ == "__main__":
    unittest.main()
