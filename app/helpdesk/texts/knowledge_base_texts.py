"""Тексты MVP базы знаний HelpDesk."""

from __future__ import annotations

from html import escape

from app.helpdesk.models.knowledge_base import KnowledgeArticle, KnowledgeScope
from app.helpdesk.repositories.location_repository import IssueCategoryRef


COMMENT_SAVE_NOTIFICATION = "Заметка сохранена.\n\nОна добавлена в базу знаний как тема:"
COMMENT_WARNING_TEXT = (
    "Не указывайте пароли, токены, приватные ссылки и персональные данные."
)
KB_UNAVAILABLE_TEXT = "База знаний сейчас недоступна."


def render_comment_prompt(
    *,
    ticket_id: str,
    category_title: str,
    object_text: str | None = None,
) -> str:
    """Форматирует prompt ввода темы заметки по заявке."""

    lines = [f"<b>Добавление заметки по заявке {escape(ticket_id)}</b>", ""]
    lines.append(f"Категория: {escape(category_title)}")
    if object_text:
        lines.append(f"Объект: {escape(object_text)}")
    lines.append("")
    lines.append("<b>Введите тему.</b>")
    return "\n".join(lines)


def render_comment_body_prompt(*, ticket_id: str, title: str) -> str:
    """Форматирует prompt ввода текста заметки по заявке."""

    return (
        f"<b>Добавление заметки по заявке {escape(ticket_id)}</b>\n\n"
        "Тема:\n"
        f"{escape(title)}\n\n"
        "Введите заметку.\n\n"
        f"{COMMENT_WARNING_TEXT}"
    )


def render_kb_scope_menu(scopes: tuple[KnowledgeScope, ...]) -> str:
    """Форматирует стартовый экран выбора раздела KB."""

    _ = scopes
    return "<b>База знаний</b>\n\nВыберите раздел:"


def render_kb_add_scope_menu(scopes: tuple[KnowledgeScope, ...]) -> str:
    """Форматирует экран выбора раздела для добавления записи."""

    _ = scopes
    return "<b>Добавление записи в базу знаний</b>\n\nВыберите раздел:"


def render_kb_scope(
    *,
    scope: KnowledgeScope,
    categories: tuple[IssueCategoryRef, ...],
) -> str:
    """Форматирует экран раздела KB."""

    lines = [f"<b>База знаний · {escape(scope.title)}</b>", ""]
    if categories:
        lines.append("Выберите категорию:")
        return "\n".join(lines)
    lines.append("Раздел пока в разработке.")
    return "\n".join(lines)


def render_kb_category(
    *,
    scope_title: str,
    category: IssueCategoryRef,
    articles: list[KnowledgeArticle],
) -> str:
    """Форматирует заголовок экрана категории KB."""

    heading = f"<b>База знаний · {escape(scope_title)} · {escape(category.title)}</b>"
    if not articles:
        return f"{heading}\n\nТем пока нет."
    return heading


def render_kb_article(
    article: KnowledgeArticle,
    *,
    scope_title: str,
    category_title: str,
) -> str:
    """Форматирует карточку одной статьи KB."""

    return "\n".join(
        [
            f"<b>База знаний · {escape(scope_title)} · {escape(category_title)}</b>",
            "",
            f"<b>{escape(article.title)}</b>",
            "",
            escape(article.body),
        ]
    )


def render_manual_article_category_prompt(scope_title: str) -> str:
    """Форматирует экран выбора категории при ручном добавлении."""

    return (
        f"<b>Добавление заметки · {escape(scope_title)}</b>\n\n"
        "Выберите категорию:"
    )


def render_manual_article_title_prompt(scope_title: str, category_title: str) -> str:
    """Форматирует prompt ввода темы."""

    return (
        f"<b>Добавление заметки · {escape(scope_title)} · {escape(category_title)}</b>\n\n"
        "Введите тему.\n\n"
        "Например:\n"
        "Не открывается страница авторизации Wi-Fi"
    )


def render_manual_article_body_prompt(scope_title: str, category_title: str, title: str) -> str:
    """Форматирует prompt ввода текста заметки."""

    return (
        f"<b>Добавление заметки · {escape(scope_title)} · {escape(category_title)}</b>\n\n"
        "Тема:\n"
        f"{escape(title)}\n\n"
        "Введите заметку.\n\n"
        f"{COMMENT_WARNING_TEXT}"
    )


def render_manual_article_saved(scope_title: str, category_title: str, title: str) -> str:
    """Форматирует ответ после сохранения ручной заметки."""

    return (
        "Заметка сохранена в базу знаний.\n\n"
        f"Раздел: {escape(scope_title)}\n"
        f"Категория: {escape(category_title)}\n"
        f"Тема: {escape(title)}\n"
        "Статус: candidate"
    )
