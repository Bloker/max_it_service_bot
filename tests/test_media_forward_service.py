import unittest
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from maxapi.enums.upload_type import UploadType
from maxapi.types import AttachmentPayload, AttachmentUpload, InputMediaBuffer

from app.bot.services.media_forward_service import MediaForwardService
from app.helpdesk.services.user_flow_service import UserDraftSourceMessage


@dataclass
class FakePayload:
    token: str | None = None
    url: str | None = None


@dataclass
class FakeAttachment:
    type: str
    payload: FakePayload | None = None


class FakeMessage:
    def __init__(
        self,
        *,
        fail_forward: bool = False,
        forwarded_mid: str | None = "forwarded-mid",
    ) -> None:
        self.fail_forward = fail_forward
        self.forwarded_mid = forwarded_mid
        self.forward_calls: list[dict] = []

    async def forward(self, **kwargs):
        self.forward_calls.append(kwargs)
        if self.fail_forward:
            raise RuntimeError("forward failed")
        return _sent_message(self.forwarded_mid)


class FakeBot:
    def __init__(self, *, send_error_first: int = 0) -> None:
        self.send_calls: list[dict] = []
        self._send_error_first = send_error_first

    async def send_message(self, **kwargs):
        self.send_calls.append(kwargs)
        if self._send_error_first > 0:
            self._send_error_first -= 1
            raise RuntimeError("send error")
        return _sent_message("fallback-mid")


def _sent_message(mid: str | None):
    return SimpleNamespace(message=SimpleNamespace(body=SimpleNamespace(mid=mid)))


class MediaForwardServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_token_resend_success_no_native_forward(self) -> None:
        service = MediaForwardService()
        message = FakeMessage()
        bot = FakeBot()
        source = UserDraftSourceMessage(
            message=message,
            message_id="source-mid",
            attachments=[FakeAttachment("audio", FakePayload(token="secret-token"))],
        )

        sent_mid = await service.forward_audio_with_fallback(
            bot=bot,
            source_message=source,
            ticket_id="T-00001",
            user_id=101,
            target_chat_id=-100,
        )

        self.assertEqual("fallback-mid", sent_mid)
        self.assertEqual([], message.forward_calls)
        self.assertEqual(1, len(bot.send_calls))
        self.assertEqual(-100, bot.send_calls[0]["chat_id"])
        attachment = bot.send_calls[0]["attachments"][0]
        self.assertIsInstance(attachment, AttachmentUpload)
        self.assertEqual(UploadType.AUDIO, attachment.type)
        self.assertEqual("secret-token", attachment.payload.token)

    async def test_token_resend_to_user_dialog(self) -> None:
        service = MediaForwardService()
        message = FakeMessage()
        bot = FakeBot()
        source = UserDraftSourceMessage(
            message=message,
            message_id="source-mid",
            attachments=[FakeAttachment("audio", FakePayload(token="secret-token"))],
        )

        sent_mid = await service.forward_audio_with_fallback(
            bot=bot,
            source_message=source,
            ticket_id="T-00004",
            user_id=404,
            target_user_id=505,
        )

        self.assertEqual("fallback-mid", sent_mid)
        self.assertEqual([], message.forward_calls)
        self.assertEqual(505, bot.send_calls[0]["user_id"])
        self.assertIsInstance(bot.send_calls[0]["attachments"][0], AttachmentUpload)

    async def test_no_token_uses_download_resend(self) -> None:
        service = MediaForwardService()
        message = FakeMessage()
        bot = FakeBot()
        source = UserDraftSourceMessage(
            message=message,
            message_id="source-mid",
            attachments=[FakeAttachment("audio", FakePayload(url="https://example.invalid/a"))],
        )

        with patch(
            "app.bot.services.media_forward_service._download_attachment_bytes",
            new=AsyncMock(return_value=b"audio-bytes"),
        ):
            sent_mid = await service.forward_audio_with_fallback(
                bot=bot,
                source_message=source,
                ticket_id="T-00005",
                user_id=505,
                target_chat_id=-500,
            )

        self.assertEqual("fallback-mid", sent_mid)
        self.assertEqual([], message.forward_calls)
        self.assertEqual(1, len(bot.send_calls))
        self.assertEqual(-500, bot.send_calls[0]["chat_id"])
        attachment = bot.send_calls[0]["attachments"][0]
        self.assertIsInstance(attachment, InputMediaBuffer)
        self.assertEqual("audio", attachment.type.value)
        self.assertEqual(b"audio-bytes", attachment.buffer)

    async def test_token_resend_failure_falls_through_to_download(self) -> None:
        service = MediaForwardService()
        message = FakeMessage()
        bot = FakeBot(send_error_first=1)
        source = UserDraftSourceMessage(
            message=message,
            message_id="source-mid",
            attachments=[
                FakeAttachment(
                    "audio",
                    FakePayload(token="secret-token", url="https://example.invalid/a"),
                )
            ],
        )

        with patch(
            "app.bot.services.media_forward_service._download_attachment_bytes",
            new=AsyncMock(return_value=b"audio-bytes"),
        ):
            sent_mid = await service.forward_audio_with_fallback(
                bot=bot,
                source_message=source,
                ticket_id="T-00006",
                user_id=606,
                target_chat_id=-600,
            )

        self.assertEqual("fallback-mid", sent_mid)
        self.assertEqual([], message.forward_calls)
        self.assertEqual(2, len(bot.send_calls))
        self.assertIsInstance(bot.send_calls[0]["attachments"][0], AttachmentUpload)
        self.assertIsInstance(bot.send_calls[1]["attachments"][0], InputMediaBuffer)

    async def test_token_and_download_fail_uses_native_forward(self) -> None:
        service = MediaForwardService()
        message = FakeMessage(forwarded_mid="native-forwarded-mid")
        bot = FakeBot(send_error_first=2)
        source = UserDraftSourceMessage(
            message=message,
            message_id="source-mid",
            attachments=[
                FakeAttachment(
                    "audio",
                    FakePayload(token="secret-token", url="https://example.invalid/a"),
                )
            ],
        )

        with patch(
            "app.bot.services.media_forward_service._download_attachment_bytes",
            new=AsyncMock(return_value=b"audio-bytes"),
        ):
            sent_mid = await service.forward_audio_with_fallback(
                bot=bot,
                source_message=source,
                ticket_id="T-00002",
                user_id=202,
                target_chat_id=-200,
            )

        self.assertEqual("native-forwarded-mid", sent_mid)
        self.assertEqual([{"chat_id": -200}], message.forward_calls)
        self.assertEqual(2, len(bot.send_calls))

    async def test_no_token_no_url_uses_native_forward(self) -> None:
        service = MediaForwardService()
        message = FakeMessage(forwarded_mid="native-forwarded-mid")
        bot = FakeBot()
        source = UserDraftSourceMessage(
            message=message,
            message_id="source-mid",
            attachments=[FakeAttachment("audio", FakePayload())],
        )

        sent_mid = await service.forward_audio_with_fallback(
            bot=bot,
            source_message=source,
            ticket_id="T-00007",
            user_id=707,
            target_chat_id=-700,
        )

        self.assertEqual("native-forwarded-mid", sent_mid)
        self.assertEqual([{"chat_id": -700}], message.forward_calls)
        self.assertEqual(0, len(bot.send_calls))

    async def test_all_methods_fail_sends_safe_notice(self) -> None:
        service = MediaForwardService()
        message = FakeMessage(fail_forward=True)
        bot = FakeBot(send_error_first=2)
        source = UserDraftSourceMessage(
            message=message,
            message_id="source-mid",
            attachments=[
                FakeAttachment(
                    "audio",
                    FakePayload(token="secret-token", url="https://example.invalid/a"),
                )
            ],
        )

        with patch(
            "app.bot.services.media_forward_service._download_attachment_bytes",
            new=AsyncMock(return_value=b"audio-bytes"),
        ):
            sent_mid = await service.forward_audio_with_fallback(
                bot=bot,
                source_message=source,
                ticket_id="T-00008",
                user_id=808,
                target_chat_id=-800,
            )

        self.assertIsNone(sent_mid)
        self.assertEqual(3, len(bot.send_calls))
        notice = bot.send_calls[2]
        self.assertEqual(-800, notice["chat_id"])
        self.assertNotIn("secret-token", notice["text"])


if __name__ == "__main__":
    unittest.main()
