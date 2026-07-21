import unittest
from dataclasses import dataclass
from types import SimpleNamespace

from maxapi.types import MessageCreated

from app.bot.handlers.messages import (
    _draft_has_problem_content,
    _extract_incoming_attachments,
    _extract_incoming_text,
    _extract_ticket_media_attachments,
    _resolve_draft_problem_text,
    build_wifi_escalation_keyboard,
)
from app.helpdesk.services.user_flow_service import UserDraft, UserDraftSourceMessage


@dataclass
class _Payload:
    token: str


@dataclass
class _Attachment:
    type: str
    payload: _Payload


def _event(*, body=None, link=None):
    return SimpleNamespace(message=SimpleNamespace(body=body, link=link))


class MessageDraftContentTests(unittest.TestCase):
    def test_wifi_room_description_prompt_keyboard_is_available(self) -> None:
        """После выбора номера обработчик может показать ввод описания."""

        self.assertTrue(build_wifi_escalation_keyboard())

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

    def test_extracts_forwarded_video_without_outer_body(self) -> None:
        video = _Attachment("video", _Payload("video-token"))
        event = _event(
            link=SimpleNamespace(
                type="forward",
                message=SimpleNamespace(
                    mid="forwarded-mid",
                    text=None,
                    attachments=[video],
                ),
            ),
        )

        attachments = _extract_ticket_media_attachments(event)

        self.assertEqual(len(attachments), 1)
        self.assertEqual(str(attachments[0].type), "video")
        self.assertEqual(attachments[0].payload.token, "video-token")

    def test_extracts_forwarded_caption_when_outer_text_is_empty(self) -> None:
        event = _event(
            body=SimpleNamespace(text="", attachments=[]),
            link=SimpleNamespace(
                type="forward",
                message=SimpleNamespace(
                    text="Не работает телевизор",
                    attachments=[],
                ),
            ),
        )

        self.assertEqual(_extract_incoming_text(event), "Не работает телевизор")

    def test_reply_attachments_are_not_added_to_new_ticket(self) -> None:
        linked_photo = _Attachment("image", _Payload("old-photo-token"))
        event = _event(
            body=SimpleNamespace(text="Новая проблема", attachments=[]),
            link=SimpleNamespace(
                type="reply",
                message=SimpleNamespace(
                    text="Старое сообщение",
                    attachments=[linked_photo],
                ),
            ),
        )

        self.assertEqual(_extract_incoming_attachments(event), [])
        self.assertEqual(_extract_incoming_text(event), "Новая проблема")

    def test_same_direct_and_forwarded_token_is_added_once(self) -> None:
        direct = _Attachment("image", _Payload("same-token"))
        forwarded = _Attachment("image", _Payload("same-token"))
        event = _event(
            body=SimpleNamespace(text="", attachments=[direct]),
            link=SimpleNamespace(
                type="forward",
                message=SimpleNamespace(text="", attachments=[forwarded]),
            ),
        )

        self.assertEqual(_extract_incoming_attachments(event), [direct])

    def test_real_maxapi_forwarded_message_model_exposes_video(self) -> None:
        event = MessageCreated.model_validate({
            "update_type": "message_created",
            "timestamp": 1,
            "message": {
                "recipient": {"user_id": 10, "chat_type": "dialog"},
                "timestamp": 1,
                "body": {"mid": "outer-mid", "seq": 1, "attachments": []},
                "link": {
                    "type": "forward",
                    "message": {
                        "mid": "source-mid",
                        "seq": 2,
                        "text": "Видео неисправности",
                        "attachments": [
                            {
                                "type": "video",
                                "payload": {
                                    "url": "https://example.invalid/private-video",
                                    "token": "forwarded-video-token",
                                },
                            }
                        ],
                    },
                },
            },
        })

        attachments = _extract_ticket_media_attachments(event)

        self.assertEqual(_extract_incoming_text(event), "Видео неисправности")
        self.assertEqual(len(attachments), 1)
        self.assertEqual(str(attachments[0].type), "video")
        self.assertEqual(attachments[0].payload.token, "forwarded-video-token")

    def test_real_maxapi_media_only_forwarded_photo_is_ticket_content(self) -> None:
        event = MessageCreated.model_validate({
            "update_type": "message_created",
            "timestamp": 1,
            "message": {
                "recipient": {"user_id": 10, "chat_type": "dialog"},
                "timestamp": 1,
                "body": {"mid": "outer-mid", "seq": 1, "attachments": []},
                "link": {
                    "type": "forward",
                    "message": {
                        "mid": "source-mid",
                        "seq": 2,
                        "attachments": [
                            {
                                "type": "image",
                                "payload": {
                                    "url": "https://example.invalid/private-photo",
                                    "token": "forwarded-photo-token",
                                    "photo_id": 42,
                                },
                            }
                        ],
                    },
                },
            },
        })

        attachments = _extract_ticket_media_attachments(event)
        draft = UserDraft(category="Интернет", attachments=attachments)

        self.assertEqual(_extract_incoming_text(event), "")
        self.assertEqual(len(attachments), 1)
        self.assertEqual(str(attachments[0].type), "image")
        self.assertTrue(_draft_has_problem_content(draft))
        self.assertEqual(_resolve_draft_problem_text(draft), "[вложение]")


if __name__ == "__main__":
    unittest.main()
