"""Проверки media attachment service."""

from __future__ import annotations

import unittest

from maxapi.enums.upload_type import UploadType
from maxapi.types import AttachmentPayload, AttachmentUpload

from app.helpdesk.models.media_attachment import MediaAttachment
from app.helpdesk.repositories.media_attachment_repository import CreateMediaAttachmentInput
from app.helpdesk.services.media_attachment_service import MediaAttachmentService


class _FakePayload:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


class _FakeAttachment:
    def __init__(self, attachment_type: str, **payload_kwargs) -> None:
        self.type = attachment_type
        self.payload = _FakePayload(**payload_kwargs)


class _FakeRepository:
    def __init__(self) -> None:
        self.items: list[MediaAttachment] = []

    def create_attachment(self, payload: CreateMediaAttachmentInput) -> MediaAttachment:
        item = MediaAttachment(
            id=len(self.items) + 1,
            owner_type=payload.owner_type,
            owner_id=payload.owner_id,
            ticket_key=payload.ticket_key,
            hotel_id=payload.hotel_id,
            location_id=payload.location_id,
            media_type=payload.media_type,
            mime_type=payload.mime_type,
            file_name=payload.file_name,
            file_size=payload.file_size,
            max_file_id=payload.max_file_id,
            max_attachment_id=payload.max_attachment_id,
            storage_path=payload.storage_path,
            public_url=payload.public_url,
            checksum=payload.checksum,
            metadata=payload.metadata,
            created_by=payload.created_by,
        )
        self.items.append(item)
        return item

    def list_attachments(self, *, owner_type: str, owner_id: int) -> list[MediaAttachment]:
        return [
            item for item in self.items if item.owner_type == owner_type and item.owner_id == owner_id
        ]


class MediaAttachmentServiceTests(unittest.TestCase):
    def test_collect_supported_accepts_photo_video_document(self) -> None:
        service = MediaAttachmentService(max_attachments_per_item=10, max_file_size_mb=50)

        result = service.collect_supported(
            0,
            [
                _FakeAttachment("photo", token="photo-token"),
                _FakeAttachment("video", token="video-token"),
                _FakeAttachment("document", token="file-token"),
            ],
        )

        self.assertEqual(3, len(result.accepted))
        self.assertEqual([], result.rejected_messages)

    def test_collect_supported_rejects_audio(self) -> None:
        service = MediaAttachmentService(max_attachments_per_item=10, max_file_size_mb=50)

        result = service.collect_supported(0, [_FakeAttachment("audio", token="audio-token")])

        self.assertEqual([], result.accepted)
        self.assertIn("Аудио и голосовые пока не поддерживаются.", result.rejected_messages)

    def test_save_many_and_count_by_type(self) -> None:
        repository = _FakeRepository()
        service = MediaAttachmentService(repository=repository)

        saved = service.save_many(
            owner_type="ticket_comment",
            owner_id=15,
            ticket_key="T-00105",
            hotel_id=1,
            location_id=112,
            attachments=[
                _FakeAttachment("photo", token="photo-token", file_name="a.jpg"),
                _FakeAttachment("document", token="doc-token", file_name="a.txt"),
            ],
            created_by=99,
            metadata={"source": "ticket_internal_comment"},
        )

        counts = service.count_attachments(owner_type="ticket_comment", owner_id=15)

        self.assertEqual(2, len(saved))
        self.assertEqual("T-00105", saved[0].ticket_key)
        self.assertEqual(1, counts.photo_count)
        self.assertEqual(1, counts.document_count)
        self.assertEqual(2, counts.total_count)

    def test_build_upload_attachments_restores_token_based_uploads(self) -> None:
        repository = _FakeRepository()
        service = MediaAttachmentService(repository=repository)
        service.save_many(
            owner_type="knowledge_article",
            owner_id=7,
            ticket_key=None,
            hotel_id=1,
            location_id=None,
            attachments=[_FakeAttachment("photo", token="photo-token")],
            created_by=99,
            metadata={"source": "manual_knowledge_article"},
        )

        uploads = service.build_upload_attachments(owner_type="knowledge_article", owner_id=7)

        self.assertEqual(1, len(uploads))
        self.assertEqual("photo-token", uploads[0].payload.token)

    def test_save_many_accepts_real_video_attachment_upload(self) -> None:
        repository = _FakeRepository()
        service = MediaAttachmentService(repository=repository)

        saved = service.save_many(
            owner_type="knowledge_article",
            owner_id=7,
            ticket_key=None,
            hotel_id=1,
            location_id=112,
            attachments=[
                AttachmentUpload(
                    type=UploadType.VIDEO,
                    payload=AttachmentPayload(token="video-token"),
                )
            ],
            created_by=99,
            metadata={"source": "manual_knowledge_article"},
        )

        counts = service.count_attachments(owner_type="knowledge_article", owner_id=7)

        self.assertEqual(1, len(saved))
        self.assertEqual("video", saved[0].media_type)
        self.assertEqual("video-token", saved[0].metadata["token"])
        self.assertEqual(1, counts.video_count)

    def test_save_many_does_not_persist_audio_when_called_directly(self) -> None:
        repository = _FakeRepository()
        service = MediaAttachmentService(repository=repository)

        saved = service.save_many(
            owner_type="ticket_comment",
            owner_id=15,
            ticket_key="T-00105",
            hotel_id=1,
            location_id=112,
            attachments=[_FakeAttachment("audio", token="audio-token")],
            created_by=99,
        )

        self.assertEqual([], saved)
        self.assertEqual([], repository.items)


if __name__ == "__main__":
    unittest.main()
