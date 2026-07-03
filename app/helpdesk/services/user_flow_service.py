"""Сервис пользовательских черновиков и шагов создания заявки."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class UserDraftSourceMessage:
    """Исходное сообщение пользователя, которое нужно переслать нативно."""

    message: Any
    message_id: str | None = None
    attachments: list[Any] = field(default_factory=list)


@dataclass(slots=True)
class UserDraft:
    """Черновик пользовательской заявки в текущем диалоге."""

    category: str | None = None
    problem_text: str | None = None
    step: str = "idle"
    attachments: list[Any] = field(default_factory=list)
    source_audio_messages: list[UserDraftSourceMessage] = field(default_factory=list)


class UserFlowService:
    """Хранит шаги пользовательского сценария создания заявки."""

    def __init__(self) -> None:
        self._drafts: dict[int, UserDraft] = {}

    def get(self, user_id: int) -> UserDraft:
        return self._drafts.setdefault(user_id, UserDraft())

    def reset(self, user_id: int) -> None:
        self._drafts[user_id] = UserDraft()

    def begin_create(self, user_id: int) -> UserDraft:
        """Начинает сценарий создания новой заявки."""

        draft = self.get(user_id)
        draft.step = "awaiting_category"
        draft.category = None
        draft.problem_text = None
        draft.attachments = []
        draft.source_audio_messages = []
        return draft

    def set_category(self, user_id: int, category: str) -> UserDraft:
        """Сохраняет выбранную категорию заявки."""

        draft = self.get(user_id)
        draft.category = category
        draft.step = "awaiting_problem_text"
        return draft

    def set_problem_text(self, user_id: int, text: str) -> UserDraft:
        """Сохраняет описание проблемы и переводит заявку к подтверждению."""

        draft = self.get(user_id)
        draft.problem_text = text
        draft.step = "awaiting_confirmation"
        return draft

    def append_problem_chunk(
        self,
        user_id: int,
        text: str | None = None,
        attachments: list[Any] | None = None,
        source_audio_messages: list[UserDraftSourceMessage] | None = None,
    ) -> UserDraft:
        """Добавляет текст или вложения к текущему черновику заявки."""

        draft = self.get(user_id)
        normalized = (text or "").strip()
        if normalized:
            if draft.problem_text:
                draft.problem_text = f"{draft.problem_text}\n{normalized}"
            else:
                draft.problem_text = normalized
        if attachments:
            draft.attachments.extend(attachments)
        if source_audio_messages:
            draft.source_audio_messages.extend(source_audio_messages)
        return draft
