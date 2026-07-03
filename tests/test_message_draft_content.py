import unittest

from app.bot.handlers.messages import (
    _draft_has_problem_content,
    _resolve_draft_problem_text,
)
from app.helpdesk.services.user_flow_service import UserDraft, UserDraftSourceMessage


class MessageDraftContentTests(unittest.TestCase):
    def test_audio_only_draft_has_content_and_safe_text(self) -> None:
        draft = UserDraft(
            category="Принтеры",
            source_audio_messages=[
                UserDraftSourceMessage(message="message", message_id="mid-1")
            ],
        )

        self.assertTrue(_draft_has_problem_content(draft))
        self.assertEqual("[аудиосообщение]", _resolve_draft_problem_text(draft))

    def test_attachment_only_draft_has_content_and_safe_text(self) -> None:
        draft = UserDraft(category="Принтеры", attachments=["photo"])

        self.assertTrue(_draft_has_problem_content(draft))
        self.assertEqual("[вложение]", _resolve_draft_problem_text(draft))

    def test_text_has_priority_over_media_placeholder(self) -> None:
        draft = UserDraft(
            category="Принтеры",
            problem_text="Не печатает",
            source_audio_messages=[
                UserDraftSourceMessage(message="message", message_id="mid-1")
            ],
        )

        self.assertTrue(_draft_has_problem_content(draft))
        self.assertEqual("Не печатает", _resolve_draft_problem_text(draft))


if __name__ == "__main__":
    unittest.main()
