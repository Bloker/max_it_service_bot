import unittest
from datetime import datetime, timezone

from maxapi.enums.upload_type import UploadType
from maxapi.types import AttachmentPayload, AttachmentUpload

from app.helpdesk.repositories.ticket_context_repository import (
    TicketAttachmentRecord,
    TicketCommentRecord,
)
from app.helpdesk.services.ticket_user_addition_service import (
    CARD_ADDITION_PREVIEW_LENGTH,
    TicketUserAdditionService,
)
from app.helpdesk.services.user_addition_session_service import UserAdditionSessionService


class FakeTicketContextRepository:
    def __init__(self) -> None:
        self.comments: list[TicketCommentRecord] = []
        self.attachments: list[TicketAttachmentRecord] = []

    def save_comment(self, **kwargs):
        item = TicketCommentRecord(
            id=len(self.comments) + 1,
            ticket_id=kwargs["ticket_id"],
            direction=kwargs["direction"],
            body=kwargs["body"],
            created_at=datetime.now(timezone.utc),
            author_user_id=kwargs.get("author_user_id"),
            author_name=kwargs.get("author_name"),
            author_role=kwargs.get("author_role"),
            source_message_id=kwargs.get("source_message_id"),
            target_message_id=kwargs.get("target_message_id"),
            meta=dict(kwargs.get("meta") or {}),
        )
        self.comments.append(item)
        return item

    def save_attachment(self, **kwargs):
        item = TicketAttachmentRecord(
            id=len(self.attachments) + 1,
            ticket_id=kwargs["ticket_id"],
            comment_id=kwargs.get("comment_id"),
            platform_attachment_type=kwargs.get("platform_attachment_type"),
            platform_attachment_ref=kwargs.get("platform_attachment_ref"),
            meta=dict(kwargs.get("meta") or {}),
        )
        self.attachments.append(item)
        return item

    def list_attachments(self, *, ticket_id, source=None, comment_id=None):
        items = [item for item in self.attachments if item.ticket_id == ticket_id]
        if source is not None:
            items = [item for item in items if item.meta.get("source") == source]
        if comment_id is not None:
            items = [item for item in items if item.comment_id == comment_id]
        return items

    def get_comment(self, comment_id):
        return next((item for item in self.comments if item.id == comment_id), None)

    def bind_comment_target_message(self, comment_id, target_message_id):
        item = self.get_comment(comment_id)
        if item:
            item.target_message_id = target_message_id
        return item

    def mark_comment_attached(self, comment_id, *, direction):
        item = self.get_comment(comment_id)
        if item and item.direction == direction:
            item.meta["attached_to_card"] = True
            return item
        return None

    def get_last_comment(self, *, ticket_id, direction, attached_to_card=None):
        items = [
            item for item in self.comments
            if item.ticket_id == ticket_id and item.direction == direction
        ]
        if attached_to_card is not None:
            items = [
                item for item in items
                if item.meta.get("attached_to_card") is attached_to_card
            ]
        return items[-1] if items else None


class TicketUserAdditionServiceTests(unittest.TestCase):
    def test_save_persists_comment_and_attachment_metadata(self) -> None:
        repository = FakeTicketContextRepository()
        service = TicketUserAdditionService(repository)
        attachment = AttachmentUpload(
            type=UploadType.IMAGE,
            payload=AttachmentPayload(token="photo-token"),
        )

        addition = service.save(
            ticket_id="T-00001",
            user_id=101,
            user_name="Иван",
            text="Дополнительное фото",
            attachments=[attachment],
            source_message_id="user-mid",
        )

        comment = repository.comments[0]
        self.assertEqual(comment.direction, "user_addition")
        self.assertEqual(comment.meta["source"], "user_addition")
        self.assertFalse(comment.meta["attached_to_card"])
        self.assertTrue(comment.meta["visible_to_user"])
        self.assertEqual(addition.ticket_id, "T-00001")
        self.assertEqual(repository.attachments[0].platform_attachment_ref, "photo-token")

    def test_attach_is_idempotent_and_latest_attached_is_restored(self) -> None:
        repository = FakeTicketContextRepository()
        service = TicketUserAdditionService(repository)
        addition = service.save(
            ticket_id="T-00002",
            user_id=102,
            user_name="Анна",
            text="Новые сведения",
        )
        service.bind_group_message(addition.comment_id, "group-mid")

        first = service.attach(addition.comment_id)
        second = service.attach(addition.comment_id)
        restored = TicketUserAdditionService(repository).get_last_attached("T-00002")

        self.assertTrue(first.attached_to_card)
        self.assertTrue(second.attached_to_card)
        self.assertEqual(first.group_message_id, "group-mid")
        self.assertEqual(restored.text, "Новые сведения")

    def test_card_preview_is_truncated(self) -> None:
        item = TicketUserAdditionService().save(
            ticket_id="T-00003",
            user_id=103,
            user_name="User",
            text="А" * (CARD_ADDITION_PREVIEW_LENGTH + 50),
        )
        self.assertTrue(item.card_text.endswith("..."))
        self.assertLessEqual(len(item.card_text), CARD_ADDITION_PREVIEW_LENGTH + 3)

    def test_repeated_additions_create_separate_records(self) -> None:
        repository = FakeTicketContextRepository()
        service = TicketUserAdditionService(repository)

        first = service.save(
            ticket_id="T-00004",
            user_id=104,
            user_name="User",
            text="Первое дополнение",
        )
        second = service.save(
            ticket_id="T-00004",
            user_id=104,
            user_name="User",
            text="Второе дополнение",
        )

        self.assertNotEqual(first.comment_id, second.comment_id)
        self.assertEqual(len(repository.comments), 2)
        self.assertEqual(repository.comments[0].body, "Первое дополнение")
        self.assertEqual(repository.comments[1].body, "Второе дополнение")

    def test_user_session_replaces_previous_and_can_be_cancelled(self) -> None:
        sessions = UserAdditionSessionService()
        sessions.start(user_id=101, ticket_id="T-00001")
        current = sessions.start(user_id=101, ticket_id="T-00002", prompt_message_id="mid")

        self.assertEqual(sessions.get(101), current)
        self.assertEqual(sessions.reset(101), current)
        self.assertIsNone(sessions.get(101))


if __name__ == "__main__":
    unittest.main()
