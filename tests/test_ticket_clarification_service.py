import unittest
from datetime import datetime, timezone

from maxapi.enums.upload_type import UploadType
from maxapi.types import AttachmentPayload, AttachmentUpload

from app.helpdesk.repositories.ticket_context_repository import (
    TicketAttachmentRecord,
    TicketCommentRecord,
)
from app.helpdesk.services.ticket_clarification_service import (
    CARD_CLARIFICATION_PREVIEW_LENGTH,
    TicketClarificationService,
)


class TicketClarificationServiceTests(unittest.TestCase):
    def test_save_and_get_last_clarification(self) -> None:
        service = TicketClarificationService()

        item = service.save_last(
            ticket_id="T-00001",
            actor_user_id=501,
            actor_name="Дмитрий",
            text="Что именно не работает?",
        )

        self.assertEqual(service.get_last("T-00001"), item)
        self.assertEqual(item.card_text, "Что именно не работает?")

    def test_card_text_is_shortened(self) -> None:
        service = TicketClarificationService()
        item = service.save_last(
            ticket_id="T-00001",
            actor_user_id=501,
            actor_name="Дмитрий",
            text="А" * (CARD_CLARIFICATION_PREVIEW_LENGTH + 20),
        )

        self.assertLessEqual(len(item.card_text), CARD_CLARIFICATION_PREVIEW_LENGTH + 3)
        self.assertTrue(item.card_text.endswith("..."))

    def test_user_reply_candidate_can_be_attached(self) -> None:
        service = TicketClarificationService()

        candidate = service.save_user_reply_candidate(
            ticket_id="T-00001",
            user_id=101,
            user_name="Пользователь",
            text="Проверил, теперь работает",
            group_message_id="group-mid-1",
            attachments=["photo-attachment"],
        )
        attached = service.attach_user_reply("group-mid-1")

        self.assertEqual(attached, candidate)
        self.assertEqual(service.get_attached_user_reply("T-00001"), candidate)
        self.assertEqual(
            service.get_user_reply_by_group_message("group-mid-1"),
            candidate,
        )
        self.assertEqual(candidate.attachments, ["photo-attachment"])

    def test_ticket_base_attachments_are_stored(self) -> None:
        service = TicketClarificationService()

        service.set_ticket_base_attachments(
            ticket_id="T-00001",
            attachments=["initial-photo"],
        )

        self.assertEqual(
            service.get_ticket_base_attachments("T-00001"),
            ["initial-photo"],
        )

    def test_save_clarification_persists_comment_and_attachment_metadata(self) -> None:
        repository = FakeTicketContextRepository()
        service = TicketClarificationService(repository=repository)
        attachment = AttachmentUpload(
            type=UploadType.IMAGE,
            payload=AttachmentPayload(token="image-token"),
        )

        service.save_last(
            ticket_id="T-00001",
            actor_user_id=501,
            actor_name="Дмитрий",
            text="Пришлите фото ошибки",
            attachments=[attachment],
            source_message_id="group-question",
            target_message_id="user-question",
        )

        self.assertEqual(1, len(repository.comments))
        comment = repository.comments[0]
        self.assertEqual("specialist_clarification", comment.direction)
        self.assertEqual("IT specialist", comment.author_role)
        self.assertEqual("group-question", comment.source_message_id)
        self.assertEqual("user-question", comment.target_message_id)
        self.assertEqual(1, len(repository.attachments))
        saved_attachment = repository.attachments[0]
        self.assertEqual("image", saved_attachment.platform_attachment_type)
        self.assertEqual("image-token", saved_attachment.platform_attachment_ref)
        self.assertNotIn("url", saved_attachment.meta)

    def test_restores_last_clarification_from_repository(self) -> None:
        repository = FakeTicketContextRepository()
        comment = repository.save_comment(
            ticket_id="T-00001",
            direction="specialist_clarification",
            body="Уточните кабинет",
            author_user_id=501,
            author_name="Дмитрий",
            author_role="IT specialist",
            meta={"attached_to_card": True},
        )
        repository.save_attachment(
            ticket_id="T-00001",
            comment_id=comment.id,
            platform_attachment_type="image",
            platform_attachment_ref="image-token",
            meta={"source": "specialist_clarification", "type": "image"},
        )
        service = TicketClarificationService(repository=repository)

        restored = service.get_last("T-00001")

        self.assertIsNotNone(restored)
        self.assertEqual("Уточните кабинет", restored.text)
        self.assertEqual("Дмитрий", restored.actor_name)
        self.assertEqual(1, len(restored.attachments))
        self.assertIsInstance(restored.attachments[0], AttachmentUpload)
        self.assertEqual("image-token", restored.attachments[0].payload.token)

    def test_user_reply_persists_and_restores_attached_reply(self) -> None:
        repository = FakeTicketContextRepository()
        service = TicketClarificationService(repository=repository)

        service.save_user_reply_candidate(
            ticket_id="T-00002",
            user_id=101,
            user_name="Пользователь",
            text="Сделал",
            group_message_id="group-reply",
            source_message_id="user-reply",
        )
        attached = service.attach_user_reply("group-reply")

        self.assertIsNotNone(attached)
        fresh_service = TicketClarificationService(repository=repository)
        restored = fresh_service.get_attached_user_reply("T-00002")
        self.assertIsNotNone(restored)
        self.assertEqual("Сделал", restored.text)
        self.assertEqual("group-reply", restored.group_message_id)
        self.assertTrue(repository.comments[0].meta["attached_to_card"])

    def test_restores_base_attachments_from_repository(self) -> None:
        repository = FakeTicketContextRepository()
        repository.save_attachment(
            ticket_id="T-00003",
            platform_attachment_type="file",
            platform_attachment_ref="file-token",
            meta={"source": "ticket_initial", "type": "file"},
        )
        service = TicketClarificationService(repository=repository)

        restored = service.get_ticket_base_attachments("T-00003")

        self.assertEqual(1, len(restored))
        self.assertIsInstance(restored[0], AttachmentUpload)
        self.assertEqual("file-token", restored[0].payload.token)


class FakeTicketContextRepository:
    def __init__(self) -> None:
        self.comments: list[TicketCommentRecord] = []
        self.attachments: list[TicketAttachmentRecord] = []
        self._next_comment_id = 1
        self._next_attachment_id = 1

    def save_comment(self, **kwargs) -> TicketCommentRecord:
        record = TicketCommentRecord(
            id=self._next_comment_id,
            ticket_id=kwargs["ticket_id"],
            direction=kwargs["direction"],
            body=kwargs["body"],
            created_at=datetime.now(tz=timezone.utc),
            author_user_id=kwargs.get("author_user_id"),
            author_name=kwargs.get("author_name"),
            author_role=kwargs.get("author_role"),
            source_message_id=kwargs.get("source_message_id"),
            target_message_id=kwargs.get("target_message_id"),
            meta=dict(kwargs.get("meta") or {}),
        )
        self._next_comment_id += 1
        self.comments.append(record)
        return record

    def save_attachment(self, **kwargs) -> TicketAttachmentRecord:
        record = TicketAttachmentRecord(
            id=self._next_attachment_id,
            ticket_id=kwargs["ticket_id"],
            comment_id=kwargs.get("comment_id"),
            platform_attachment_type=kwargs.get("platform_attachment_type"),
            platform_attachment_ref=kwargs.get("platform_attachment_ref"),
            meta=dict(kwargs.get("meta") or {}),
        )
        self._next_attachment_id += 1
        self.attachments.append(record)
        return record

    def list_attachments(
        self,
        *,
        ticket_id: str,
        source: str | None = None,
        comment_id: int | None = None,
    ) -> list[TicketAttachmentRecord]:
        result = [item for item in self.attachments if item.ticket_id == ticket_id]
        if source is not None:
            result = [item for item in result if item.meta.get("source") == source]
        if comment_id is not None:
            result = [item for item in result if item.comment_id == comment_id]
        return result

    def get_last_comment(
        self,
        *,
        ticket_id: str,
        direction: str,
        attached_to_card: bool | None = None,
    ) -> TicketCommentRecord | None:
        candidates = [
            item
            for item in self.comments
            if item.ticket_id == ticket_id and item.direction == direction
        ]
        if attached_to_card is not None:
            candidates = [
                item
                for item in candidates
                if item.meta.get("attached_to_card") is attached_to_card
            ]
        return candidates[-1] if candidates else None

    def get_user_reply_by_group_message(
        self,
        group_message_id: str,
    ) -> TicketCommentRecord | None:
        for item in reversed(self.comments):
            if item.direction == "user_reply" and item.target_message_id == group_message_id:
                return item
        return None

    def mark_user_reply_attached(self, group_message_id: str) -> TicketCommentRecord | None:
        item = self.get_user_reply_by_group_message(group_message_id)
        if item is not None:
            item.meta["attached_to_card"] = True
        return item


if __name__ == "__main__":
    unittest.main()
