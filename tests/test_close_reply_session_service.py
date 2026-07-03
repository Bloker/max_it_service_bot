import unittest
from datetime import datetime, timedelta, timezone

from app.helpdesk.services.close_reply_session_service import CloseReplySessionService


class CloseReplySessionServiceTests(unittest.TestCase):
    def test_start_get_finish_and_cancel(self) -> None:
        service = CloseReplySessionService()

        session = service.start(
            actor_user_id=101,
            actor_name="Дмитрий",
            ticket_id="T-00001",
            group_chat_id=-1,
            prompt_message_id="prompt-mid",
        )

        self.assertEqual(service.get(101), session)
        self.assertEqual(service.get_by_ticket("T-00001"), session)
        self.assertEqual(session.prompt_message_id, "prompt-mid")
        self.assertEqual(service.finish(101), session)
        self.assertIsNone(service.get(101))

        second = service.start(
            actor_user_id=102,
            actor_name="Анна",
            ticket_id="T-00002",
        )
        self.assertEqual(service.cancel(102), second)
        self.assertIsNone(service.get_by_ticket("T-00002"))

    def test_cleanup_expired_removes_old_sessions(self) -> None:
        service = CloseReplySessionService(ttl_seconds=1)
        session = service.start(
            actor_user_id=101,
            actor_name="Дмитрий",
            ticket_id="T-00001",
        )
        session.started_at = datetime.now(tz=timezone.utc) - timedelta(seconds=10)

        self.assertEqual(service.cleanup_expired(), 1)
        self.assertIsNone(service.get(101))

    def test_other_actor_cannot_finish_existing_session_by_lookup(self) -> None:
        service = CloseReplySessionService()
        session = service.start(
            actor_user_id=101,
            actor_name="Дмитрий",
            ticket_id="T-00001",
        )

        self.assertEqual(service.get_by_ticket("T-00001"), session)
        self.assertIsNone(service.finish(202))
        self.assertEqual(service.get_by_ticket("T-00001"), session)


if __name__ == "__main__":
    unittest.main()
