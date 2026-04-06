import unittest

from app.helpdesk.services.ticket_link_service import TicketLinkService


class TicketLinkServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = TicketLinkService()

    def test_primary_group_message_not_overridden_by_non_primary(self) -> None:
        self.service.bind_group_message("T-00001", "group-root", primary=True)
        self.service.bind_group_message("T-00001", "group-reply")

        self.assertEqual("group-root", self.service.get_group_message_id("T-00001"))
        self.assertEqual("T-00001", self.service.get_ticket_id_by_group_message("group-root"))
        self.assertEqual("T-00001", self.service.get_ticket_id_by_group_message("group-reply"))

    def test_user_message_mapping(self) -> None:
        self.service.bind_user_message("T-00002", "user-mid-1")
        self.assertEqual("T-00002", self.service.get_ticket_id_by_user_message("user-mid-1"))


if __name__ == "__main__":
    unittest.main()
