import unittest

from app.admin.services.access_service import (
    can_change_ticket_status,
    can_take_ticket,
    can_use_network_tools,
    can_view_service_functions,
    can_view_user_menu,
)
from app.helpdesk.models.ticket import Ticket


class AccessServiceTests(unittest.TestCase):
    def test_user_menu_visibility(self) -> None:
        self.assertTrue(can_view_user_menu(1, admin_ids=(), specialist_ids=(), user_ids=()))
        self.assertFalse(can_view_user_menu(0, admin_ids=(), specialist_ids=(), user_ids=()))

    def test_user_menu_visibility_allowlist_mode(self) -> None:
        admin_ids = (10,)
        specialist_ids = (20,)
        user_ids = (30,)
        self.assertTrue(
            can_view_user_menu(10, admin_ids=admin_ids, specialist_ids=specialist_ids, user_ids=user_ids)
        )
        self.assertTrue(
            can_view_user_menu(20, admin_ids=admin_ids, specialist_ids=specialist_ids, user_ids=user_ids)
        )
        self.assertTrue(
            can_view_user_menu(30, admin_ids=admin_ids, specialist_ids=specialist_ids, user_ids=user_ids)
        )
        self.assertFalse(
            can_view_user_menu(40, admin_ids=admin_ids, specialist_ids=specialist_ids, user_ids=user_ids)
        )

    def test_service_functions_visibility(self) -> None:
        admin_ids = (10,)
        specialist_ids = (20,)
        self.assertTrue(can_view_service_functions(10, admin_ids, specialist_ids))
        self.assertTrue(can_view_service_functions(20, admin_ids, specialist_ids))
        self.assertFalse(can_view_service_functions(30, admin_ids, specialist_ids))

    def test_network_tools_access_follows_service_access(self) -> None:
        admin_ids = (10,)
        specialist_ids = (20,)
        self.assertTrue(can_use_network_tools(20, admin_ids, specialist_ids))
        self.assertFalse(can_use_network_tools(30, admin_ids, specialist_ids))

    def test_take_ticket_access(self) -> None:
        admin_ids = (10,)
        specialist_ids = (20,)
        self.assertTrue(can_take_ticket(10, admin_ids, specialist_ids))
        self.assertTrue(can_take_ticket(20, admin_ids, specialist_ids))
        self.assertFalse(can_take_ticket(30, admin_ids, specialist_ids))

    def test_change_ticket_status_rules(self) -> None:
        admin_ids = (10,)
        specialist_ids = (20,)

        unassigned = Ticket(id='T-1', user_id=1, category='x', text='y')
        assigned = Ticket(id='T-2', user_id=1, category='x', text='y', assigned_to=20)

        self.assertTrue(can_change_ticket_status(10, assigned, admin_ids, specialist_ids))
        self.assertTrue(can_change_ticket_status(20, unassigned, admin_ids, specialist_ids))
        self.assertTrue(can_change_ticket_status(20, assigned, admin_ids, specialist_ids))
        self.assertFalse(can_change_ticket_status(30, assigned, admin_ids, specialist_ids))


if __name__ == '__main__':
    unittest.main()
