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
    hotel_id: int | None = None
    hotel_code: str | None = None
    location_id: int | None = None
    location_display: str | None = None
    room_number: str | None = None
    issue_category_id: int | None = None
    issue_category_code: str | None = None
    issue_category_title: str | None = None
    is_room_ticket_flow: bool = False


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
        self._reset_room_context(draft)
        return draft

    def begin_room_ticket(self, user_id: int, *, hotel_id: int, hotel_code: str) -> UserDraft:
        """Начинает hotel-specific сценарий заявки по номеру."""

        draft = self.get(user_id)
        draft.step = "awaiting_room_number"
        draft.category = None
        draft.problem_text = None
        draft.attachments = []
        draft.source_audio_messages = []
        self._reset_room_context(draft)
        draft.hotel_id = hotel_id
        draft.hotel_code = hotel_code
        draft.is_room_ticket_flow = True
        return draft

    def set_room_ticket_location(
        self,
        user_id: int,
        *,
        location_id: int,
        room_number: str,
        location_display: str,
    ) -> UserDraft:
        """Сохраняет выбранный номер или домик заявки."""

        draft = self.get(user_id)
        draft.location_id = location_id
        draft.room_number = room_number
        draft.location_display = location_display
        draft.step = "awaiting_room_issue_category"
        return draft

    def set_room_ticket_category(
        self,
        user_id: int,
        *,
        category_id: int,
        category_code: str,
        category_title: str,
    ) -> UserDraft:
        """Сохраняет hotel-specific категорию и ожидает описание."""

        draft = self.get(user_id)
        draft.category = category_title
        draft.issue_category_id = category_id
        draft.issue_category_code = category_code
        draft.issue_category_title = category_title
        draft.step = "awaiting_problem_text"
        return draft

    def begin_room_ticket_other(
        self,
        user_id: int,
        *,
        hotel_id: int,
        hotel_code: str,
        category_id: int | None,
        category_code: str,
        category_title: str,
    ) -> UserDraft:
        """Начинает заявку 'Прочее' без привязки к номеру."""

        draft = self.get(user_id)
        draft.step = "awaiting_problem_text"
        draft.category = category_title
        draft.problem_text = None
        draft.attachments = []
        draft.source_audio_messages = []
        self._reset_room_context(draft)
        draft.hotel_id = hotel_id
        draft.hotel_code = hotel_code
        draft.issue_category_id = category_id
        draft.issue_category_code = category_code
        draft.issue_category_title = category_title
        draft.is_room_ticket_flow = True
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

    def _reset_room_context(self, draft: UserDraft) -> None:
        """Очищает hotel-specific поля черновика."""

        draft.hotel_id = None
        draft.hotel_code = None
        draft.location_id = None
        draft.location_display = None
        draft.room_number = None
        draft.issue_category_id = None
        draft.issue_category_code = None
        draft.issue_category_title = None
        draft.is_room_ticket_flow = False
