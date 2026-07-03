import unittest
from dataclasses import dataclass

from maxapi.types import AttachmentUpload

from app.helpdesk.services.attachment_filter_service import (
    collect_ticket_media_attachments,
    is_audio_attachment,
    is_ticket_media_attachment,
    normalize_ticket_media_attachment,
)


@dataclass
class FakeAttachment:
    type: str
    payload: object | None = None


@dataclass
class FakePayload:
    token: str | None = None
    url: str | None = None


class AttachmentFilterServiceTests(unittest.TestCase):
    def test_allows_audio_and_voice_attachments(self) -> None:
        attachments = [
            FakeAttachment("audio"),
            FakeAttachment("voice_message"),
            FakeAttachment("audiomsg"),
        ]

        self.assertEqual(collect_ticket_media_attachments(attachments), attachments)

    def test_normalizes_voice_message_to_audio_upload(self) -> None:
        attachment = FakeAttachment(
            "voice_message",
            payload=FakePayload(token="voice-token", url="https://example.invalid/audio"),
        )

        normalized = normalize_ticket_media_attachment(attachment)

        self.assertIsInstance(normalized, AttachmentUpload)
        self.assertEqual(normalized.type, "audio")
        self.assertEqual(normalized.payload.token, "voice-token")

    def test_normalizes_audio_attachment_to_upload_payload(self) -> None:
        attachment = FakeAttachment(
            "audio",
            payload=FakePayload(token="audio-token", url="https://example.invalid/audio"),
        )

        normalized = collect_ticket_media_attachments([attachment])

        self.assertEqual(len(normalized), 1)
        self.assertIsInstance(normalized[0], AttachmentUpload)
        self.assertEqual(normalized[0].model_dump(), {
            "type": "audio",
            "payload": {"token": "audio-token"},
        })

    def test_can_exclude_audio_from_ticket_card_attachments(self) -> None:
        attachments = [
            FakeAttachment(
                "audio",
                payload=FakePayload(token="audio-token", url="https://example.invalid/audio"),
            ),
            FakeAttachment(
                "image",
                payload=FakePayload(token="image-token", url="https://example.invalid/image"),
            ),
        ]

        normalized = collect_ticket_media_attachments(attachments, include_audio=False)

        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0].type, "image")

    def test_detects_voice_file_by_audio_url(self) -> None:
        attachment = FakeAttachment(
            "file",
            payload=FakePayload(token="file-token", url="https://example.invalid/voice.ogg"),
        )

        self.assertTrue(is_audio_attachment(attachment))
        self.assertEqual(
            collect_ticket_media_attachments([attachment], include_audio=False),
            [],
        )

    def test_detects_voice_file_by_payload_metadata(self) -> None:
        @dataclass
        class PayloadWithMime:
            token: str | None = None
            url: str | None = None
            content_type: str | None = None

        attachment = FakeAttachment(
            "file",
            payload=PayloadWithMime(
                token="file-token",
                url="https://example.invalid/private-download",
                content_type="audio/ogg",
            ),
        )

        self.assertTrue(is_audio_attachment(attachment))
        self.assertEqual(
            collect_ticket_media_attachments([attachment], include_audio=False),
            [],
        )

    def test_allows_regular_media_and_files(self) -> None:
        attachments = [
            FakeAttachment("image"),
            FakeAttachment("video"),
            FakeAttachment("file"),
            FakeAttachment("document"),
        ]

        self.assertEqual(collect_ticket_media_attachments(attachments), attachments)

    def test_rejects_non_forwardable_attachments(self) -> None:
        for attachment_type in ("contact", "sticker", "inline_keyboard", "button"):
            self.assertFalse(is_ticket_media_attachment(FakeAttachment(attachment_type)))


if __name__ == "__main__":
    unittest.main()
