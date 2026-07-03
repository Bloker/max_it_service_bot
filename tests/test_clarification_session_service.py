import unittest

from app.helpdesk.services.clarification_session_service import (
    ClarificationSessionService,
)


class ClarificationSessionServiceTests(unittest.TestCase):
    def test_start_get_pop_and_reset_session(self) -> None:
        service = ClarificationSessionService()

        session = service.start(
            actor_user_id=501,
            actor_name="Spec",
            ticket_id="T-00001",
            group_chat_id=-100,
        )

        self.assertEqual(session.ticket_id, "T-00001")
        self.assertEqual(session.actor_user_id, 501)
        self.assertEqual(session.group_chat_id, -100)
        self.assertTrue(session.session_id)
        service.set_prompt_message_id(501, "prompt-mid")
        self.assertEqual(session.prompt_message_id, "prompt-mid")
        self.assertEqual(service.get_by_ticket("T-00001"), session)
        self.assertEqual(service.get(501), session)
        self.assertEqual(service.pop(501), session)
        self.assertIsNone(service.get(501))

        service.start(actor_user_id=501, actor_name="Spec", ticket_id="T-00002")
        service.reset(501)
        self.assertIsNone(service.get(501))


if __name__ == "__main__":
    unittest.main()
