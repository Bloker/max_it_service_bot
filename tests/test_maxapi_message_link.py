"""Проверки совместимости ссылок на сообщения в maxapi 1.2.2."""

import base64
import unittest

from maxapi.enums.chat_type import ChatType
from maxapi.types import Message
from maxapi.types.message import MessageBody, Recipient
from maxapi.utils.message_link import build_message_link


def _build_mid(chat_id: int, seq: int) -> str:
    """Собирает тестовый mid без использования реальных идентификаторов MAX."""

    unsigned_chat_id = chat_id & ((1 << 64) - 1)
    return f"mid.{unsigned_chat_id:016x}{seq:016x}"


def _expected_link(chat_id: int, seq: int) -> str:
    encoded_seq = base64.urlsafe_b64encode(seq.to_bytes(8, "big")).decode().rstrip("=")
    return f"https://max.ru/c/{chat_id}/{encoded_seq}"


class MaxApiMessageLinkTests(unittest.TestCase):
    def test_build_message_link_supports_negative_group_chat_id(self) -> None:
        chat_id = -123456789
        seq = 987654321

        result = build_message_link(_build_mid(chat_id, seq))

        self.assertEqual(result, _expected_link(chat_id, seq))

    def test_message_url_is_built_from_body_mid(self) -> None:
        chat_id = -987654321
        seq = 123456789
        mid = _build_mid(chat_id, seq)
        message = Message(
            recipient=Recipient(chat_id=chat_id, chat_type=ChatType.CHAT),
            timestamp=1,
            body=MessageBody(mid=mid, seq=seq),
        )

        self.assertEqual(message.url, _expected_link(chat_id, seq))

    def test_message_url_prefers_api_provided_url(self) -> None:
        api_url = "https://max.ru/channel/example"
        message = Message(
            recipient=Recipient(chat_id=-1, chat_type=ChatType.CHANNEL),
            timestamp=1,
            url=api_url,
        )

        self.assertEqual(message.url, api_url)

    def test_message_without_body_or_api_url_has_no_url(self) -> None:
        message = Message(
            recipient=Recipient(chat_id=-1, chat_type=ChatType.CHAT),
            timestamp=1,
        )

        self.assertIsNone(message.url)

    def test_build_message_link_rejects_invalid_mid(self) -> None:
        for invalid_mid in ("", "mid.invalid", "mid." + "0" * 31):
            with self.subTest(mid=invalid_mid):
                with self.assertRaises(ValueError):
                    build_message_link(invalid_mid)

        with self.assertRaises(TypeError):
            build_message_link(None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
