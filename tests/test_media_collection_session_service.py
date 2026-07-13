"""Проверки 15-секундных media session."""

from __future__ import annotations

import unittest
from datetime import timedelta
import asyncio

from app.helpdesk.services.media_collection_session_service import MediaCollectionSessionService


class MediaCollectionSessionServiceTests(unittest.TestCase):
    def test_append_extends_deadline_and_accumulates_chunks(self) -> None:
        service = MediaCollectionSessionService(collection_window_sec=15)
        session = service.start(actor_user_id=10, chat_id=100, state="collecting_ticket_comment")
        initial_deadline = session.deadline_at

        service.append(10, text="line 1", media=["img1"])
        updated = service.append(10, text="line 2", media=["img2"])

        self.assertIsNotNone(updated)
        self.assertEqual("line 1\nline 2", updated.body_text)
        self.assertEqual(["img1", "img2"], updated.pending_media)
        self.assertGreater(updated.deadline_at, initial_deadline)

    def test_pop_if_due_returns_session_after_deadline(self) -> None:
        service = MediaCollectionSessionService(collection_window_sec=15)
        session = service.start(actor_user_id=10, chat_id=100, state="collecting_ticket_comment")
        session.deadline_at = session.deadline_at - timedelta(seconds=16)

        popped = service.pop_if_due(10, session.session_id)

        self.assertIsNotNone(popped)
        self.assertIsNone(service.get(10))

    def test_tracks_and_deduplicates_transient_message_ids(self) -> None:
        service = MediaCollectionSessionService(collection_window_sec=15)
        session = service.start(
            actor_user_id=10,
            chat_id=100,
            state="collecting_ticket_comment",
            transient_message_ids=["prompt-1"],
        )

        updated = service.append(
            10,
            text="line 1",
            transient_message_ids=["msg-1", "prompt-1", "msg-2"],
        )

        self.assertIsNotNone(updated)
        self.assertEqual(["prompt-1", "msg-1", "msg-2"], updated.transient_message_ids)


class MediaCollectionSessionAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_finish_does_not_cancel_current_finalize_task(self) -> None:
        service = MediaCollectionSessionService(collection_window_sec=15)
        session = service.start(actor_user_id=10, chat_id=100, state="collecting_ticket_comment")

        async def runner() -> bool:
            service.set_finalize_task(10, asyncio.current_task())
            session.deadline_at = session.deadline_at - timedelta(seconds=16)
            popped = service.pop_if_due(10, session.session_id)
            return popped is not None

        result = await runner()

        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
