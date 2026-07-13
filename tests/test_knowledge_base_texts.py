"""Проверки текстов базы знаний."""

from __future__ import annotations

import unittest

from app.helpdesk.models.media_attachment import MediaAttachmentCounts
from app.helpdesk.models.knowledge_base import KnowledgeArticle
from app.helpdesk.repositories.location_repository import IssueCategoryRef
from app.helpdesk.texts.knowledge_base_texts import (
    render_comment_prompt,
    render_kb_article,
    render_kb_category,
    render_manual_article_saved,
    render_media_collection_prompt,
)


class KnowledgeBaseTextsTests(unittest.TestCase):
    """Проверяет компактное представление экранов KB."""

    def test_category_screen_contains_only_heading(self) -> None:
        """Список тем отображается кнопками, а не текстом сообщения."""

        category = IssueCategoryRef(10, "tv", "ТВ", True, 10)
        article = KnowledgeArticle(
            id=1,
            scope_id=1,
            hotel_id=1,
            category_id=10,
            title="Нет сигнала",
            body="Проверить кабель.",
            source_ticket_key=None,
            source_location_id=None,
            author_user_id=1,
            is_active=True,
            sort_order=0,
            metadata={},
            created_at=None,
            updated_at=None,
        )

        text = render_kb_category(
            scope_title="Джамайка",
            category=category,
            articles=[article],
        )

        self.assertEqual(text, "<b>База знаний · Джамайка · ТВ</b>")

    def test_ticket_note_prompt_uses_bold_title_instruction_without_example(self) -> None:
        """Первый шаг заметки показывает только жирную инструкцию ввода темы."""

        text = render_comment_prompt(
            ticket_id="T-00001",
            category_title="ТВ",
            object_text="Номер 112 (ТВ)",
        )

        self.assertIn("<b>Введите тему.</b>", text)
        self.assertNotIn("Например", text)
        self.assertNotIn("Нет гудка", text)

    def test_article_card_hides_service_fields(self) -> None:
        """Карточка KB показывает только тему и текст записи."""

        article = KnowledgeArticle(
            id=1,
            scope_id=1,
            hotel_id=1,
            category_id=10,
            title="Приставка висит на запуске",
            body="Нужно перепрошить приставку",
            source_ticket_key="T-00101",
            source_location_id=12,
            author_user_id=1,
            is_active=True,
            sort_order=0,
            metadata={},
            created_at=None,
            updated_at=None,
        )

        text = render_kb_article(
            article,
            scope_title="Джамайка",
            category_title="ТВ",
        )

        self.assertNotIn("Источник:", text)
        self.assertNotIn("Объект:", text)
        self.assertNotIn("Статус:", text)
        self.assertNotIn("candidate", text)
        self.assertNotIn("internal", text)
        self.assertIn("Нужно перепрошить приставку", text)

    def test_article_card_can_show_attachment_counts(self) -> None:
        article = KnowledgeArticle(
            id=1,
            scope_id=1,
            hotel_id=1,
            category_id=10,
            title="Приставка висит на запуске",
            body="Нужно перепрошить приставку",
        )

        text = render_kb_article(
            article,
            scope_title="Джамайка",
            category_title="ТВ",
            attachment_counts=MediaAttachmentCounts(photo_count=1, document_count=1),
        )

        self.assertIn("Вложения:", text)
        self.assertIn("Фото: 1", text)
        self.assertIn("Файлы: 1", text)

    def test_empty_category_screen_shows_empty_message(self) -> None:
        """Пустая категория явно сообщает об отсутствии тем."""

        text = render_kb_category(
            scope_title="Джамайка",
            category=IssueCategoryRef(10, "tv", "ТВ", True, 10),
            articles=[],
        )

        self.assertIn("Тем пока нет.", text)

    def test_media_collection_prompt_mentions_15_seconds(self) -> None:
        text = render_media_collection_prompt(title="Нет сигнала")

        self.assertIn("15 секунд", text)
        self.assertIn("фото, видео или файл", text)

    def test_manual_article_saved_no_longer_shows_candidate_status(self) -> None:
        text = render_manual_article_saved("Джамайка", "ТВ", "Нет сигнала")

        self.assertNotIn("candidate", text)
        self.assertNotIn("Статус:", text)


if __name__ == "__main__":
    unittest.main()
