from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class UserDraft:
    category: str | None = None
    problem_text: str | None = None
    step: str = "idle"
    attachments: list[Any] = field(default_factory=list)


class UserFlowService:
    def __init__(self) -> None:
        self._drafts: dict[int, UserDraft] = {}

    def get(self, user_id: int) -> UserDraft:
        return self._drafts.setdefault(user_id, UserDraft())

    def reset(self, user_id: int) -> None:
        self._drafts[user_id] = UserDraft()

    def begin_create(self, user_id: int) -> UserDraft:
        draft = self.get(user_id)
        draft.step = "awaiting_category"
        draft.category = None
        draft.problem_text = None
        draft.attachments = []
        return draft

    def set_category(self, user_id: int, category: str) -> UserDraft:
        draft = self.get(user_id)
        draft.category = category
        draft.step = "awaiting_problem_text"
        return draft

    def set_problem_text(self, user_id: int, text: str) -> UserDraft:
        draft = self.get(user_id)
        draft.problem_text = text
        draft.step = "awaiting_confirmation"
        return draft

    def append_problem_chunk(
        self,
        user_id: int,
        text: str | None = None,
        attachments: list[Any] | None = None,
    ) -> UserDraft:
        draft = self.get(user_id)
        normalized = (text or "").strip()
        if normalized:
            if draft.problem_text:
                draft.problem_text = f"{draft.problem_text}\n{normalized}"
            else:
                draft.problem_text = normalized
        if attachments:
            draft.attachments.extend(attachments)
        return draft

