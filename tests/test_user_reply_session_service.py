import unittest

from app.helpdesk.services.user_reply_session_service import UserReplySessionService


class UserReplySessionServiceTests(unittest.TestCase):
    def test_start_get_and_reset_session(self) -> None:
        service = UserReplySessionService()

        session = service.start(user_id=101, ticket_id="T-00001")

        self.assertEqual(session.user_id, 101)
        self.assertEqual(session.ticket_id, "T-00001")
        self.assertTrue(session.session_id)
        self.assertEqual(service.get(101), session)

        service.reset(101)
        self.assertIsNone(service.get(101))


if __name__ == "__main__":
    unittest.main()
