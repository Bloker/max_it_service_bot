import unittest

from app.helpdesk.services.user_flow_service import (
    UserDraftSourceMessage,
    UserFlowService,
)


class UserFlowServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = UserFlowService()

    def test_begin_create_resets_text_and_attachments(self) -> None:
        user_id = 101
        self.service.begin_create(user_id)
        self.service.append_problem_chunk(
            user_id,
            text="first",
            attachments=["a1"],
            source_audio_messages=[
                UserDraftSourceMessage(message="message", message_id="mid-1")
            ],
        )

        draft = self.service.begin_create(user_id)
        self.assertEqual("awaiting_category", draft.step)
        self.assertIsNone(draft.category)
        self.assertIsNone(draft.problem_text)
        self.assertEqual([], draft.attachments)
        self.assertEqual([], draft.source_audio_messages)

    def test_append_problem_chunk_accumulates_text_and_attachments(self) -> None:
        user_id = 202
        self.service.begin_create(user_id)
        self.service.set_category(user_id, "VPN")

        draft = self.service.append_problem_chunk(user_id, text="line 1", attachments=["img1"])
        draft = self.service.append_problem_chunk(user_id, text="line 2", attachments=["img2"])

        self.assertEqual("line 1\nline 2", draft.problem_text)
        self.assertEqual(["img1", "img2"], draft.attachments)

    def test_append_problem_chunk_accumulates_source_audio_messages(self) -> None:
        user_id = 303
        self.service.begin_create(user_id)
        source = UserDraftSourceMessage(message="message", message_id="mid-1")

        draft = self.service.append_problem_chunk(
            user_id,
            text="voice",
            source_audio_messages=[source],
        )

        self.assertEqual([source], draft.source_audio_messages)

    def test_room_ticket_flow_keeps_location_category_context(self) -> None:
        user_id = 404

        draft = self.service.begin_room_ticket(
            user_id,
            hotel_id=10,
            hotel_code="jamaica",
        )
        self.assertEqual("awaiting_room_number", draft.step)
        self.assertTrue(draft.is_room_ticket_flow)

        draft = self.service.set_room_ticket_location(
            user_id,
            location_id=20,
            room_number="2105",
            location_display="Корпус 2, номер 2105",
        )
        self.assertEqual("awaiting_room_issue_category", draft.step)
        self.assertEqual("2105", draft.room_number)

        draft = self.service.set_room_ticket_category(
            user_id,
            category_id=30,
            category_code="internet",
            category_title="Интернет",
        )
        self.assertEqual("awaiting_problem_text", draft.step)
        self.assertEqual("Интернет", draft.category)
        self.assertEqual(30, draft.issue_category_id)

    def test_begin_create_clears_room_ticket_context(self) -> None:
        user_id = 505
        self.service.begin_room_ticket(user_id, hotel_id=10, hotel_code="jamaica")
        self.service.set_room_ticket_location(
            user_id,
            location_id=20,
            room_number="101",
            location_display="Корпус 1, номер 101",
        )

        draft = self.service.begin_create(user_id)

        self.assertFalse(draft.is_room_ticket_flow)
        self.assertIsNone(draft.hotel_id)
        self.assertIsNone(draft.location_id)
        self.assertIsNone(draft.issue_category_id)

    def test_begin_room_ticket_other_keeps_hotel_and_has_no_location(self) -> None:
        user_id = 606

        draft = self.service.begin_room_ticket_other(
            user_id,
            hotel_id=10,
            hotel_code="jamaica",
            category_id=50,
            category_code="other",
            category_title="Прочее",
        )

        self.assertEqual("awaiting_problem_text", draft.step)
        self.assertEqual("Прочее", draft.category)
        self.assertEqual(10, draft.hotel_id)
        self.assertIsNone(draft.location_id)
        self.assertIsNone(draft.room_number)
        self.assertEqual(50, draft.issue_category_id)


if __name__ == "__main__":
    unittest.main()
