"""Файловое хранение пользователей, ролей и заявок на доступ."""

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class PendingAccessRequest:
    """Заявка пользователя на доступ к боту."""

    user_id: int
    user_name: str
    phone: str | None
    requested_at: str


@dataclass(frozen=True)
class RegisteredUser:
    """Зарегистрированный пользователь и его роль в боте."""

    user_id: int
    user_name: str
    phone: str | None
    hotel_code: str | None
    role: str
    status: str
    created_at: str
    updated_at: str


ALLOWED_ROLES = ("user", "IT specialist", "admin")
HOTEL_LABELS: dict[str, str] = {
    "jamaica": "Отель Джамайка",
    "old_anapa": "Отель Старинная Анапа",
}
HOTEL_FEATURES: dict[str, tuple[str, ...]] = {
    "jamaica": ("wifi_guest_issue", "tv_guest_issue"),
    "old_anapa": ("wifi_guest_issue",),
}


class UserAccessRegistry:
    """Файловый реестр пользователей, ролей и заявок на доступ."""

    def __init__(self, storage_path: str) -> None:
        self._path = Path(storage_path)
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict:
        """Читает JSON-реестр и нормализует поврежденные секции."""

        if not self._path.exists():
            return {"approved": [], "pending": {}, "users": {}}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return {"approved": [], "pending": {}, "users": {}}
        approved = raw.get("approved", [])
        pending = raw.get("pending", {})
        users = raw.get("users", {})
        if not isinstance(approved, list):
            approved = []
        if not isinstance(pending, dict):
            pending = {}
        if not isinstance(users, dict):
            users = {}
        return {"approved": approved, "pending": pending, "users": users}

    def _save(self, data: dict) -> None:
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_approved_ids(self) -> tuple[int, ...]:
        with self._lock:
            data = self._load()
            approved = {int(value) for value in data["approved"]}
            for raw_user_id, item in data["users"].items():
                try:
                    user_id = int(raw_user_id)
                except ValueError:
                    continue
                status = str(item.get("status", "active"))
                if status == "active":
                    approved.add(user_id)
            return tuple(sorted(approved))

    def get_banned_ids(self) -> tuple[int, ...]:
        with self._lock:
            data = self._load()
            banned: set[int] = set()
            for raw_user_id, item in data["users"].items():
                try:
                    user_id = int(raw_user_id)
                except ValueError:
                    continue
                status = str(item.get("status", "active"))
                if status == "banned":
                    banned.add(user_id)
            return tuple(sorted(banned))

    def is_approved(self, user_id: int) -> bool:
        return user_id in set(self.get_approved_ids())

    def request_access(self, user_id: int, user_name: str, phone: str | None = None) -> str:
        """Создает заявку на доступ, если пользователь еще не одобрен."""

        with self._lock:
            data = self._load()
            approved = set(int(value) for value in data["approved"])
            if user_id in approved:
                return "already_approved"
            existing_user = data["users"].get(str(user_id))
            if existing_user and str(existing_user.get("status", "active")) == "active":
                return "already_approved"

            key = str(user_id)
            pending = data["pending"]
            if key in pending:
                return "already_pending"

            pending[key] = {
                "user_name": user_name,
                "phone": phone,
                "requested_at": datetime.now(timezone.utc).isoformat(),
            }
            self._save(data)
            return "created"

    def approve(self, user_id: int, role: str = "user") -> str:
        """Одобряет pending-заявку и назначает роль."""

        with self._lock:
            data = self._load()
            normalized_role = self._normalize_role(role)
            if not normalized_role:
                return "invalid_role"

            approved = set(int(value) for value in data["approved"])
            if user_id in approved:
                return "already_approved"
            existing_user = data["users"].get(str(user_id))
            if existing_user and str(existing_user.get("status", "active")) == "active":
                return "already_approved"

            key = str(user_id)
            pending = data["pending"]
            if key not in pending:
                return "not_found"

            approved.add(user_id)
            data["approved"] = sorted(approved)
            pending_data = pending.get(key, {})
            now = datetime.now(timezone.utc).isoformat()
            data["users"][key] = {
                "user_name": str(pending_data.get("user_name", f"ID {user_id}")),
                "phone": pending_data.get("phone"),
                "hotel_code": None,
                "role": normalized_role,
                "status": "active",
                "created_at": str(pending_data.get("requested_at", now)),
                "updated_at": now,
            }
            pending.pop(key, None)
            self._save(data)
            return "approved"

    def reject(self, user_id: int) -> str:
        with self._lock:
            data = self._load()
            key = str(user_id)
            pending = data["pending"]
            if key not in pending:
                return "not_found"
            pending.pop(key, None)
            self._save(data)
            return "rejected"

    def list_users(self) -> list[RegisteredUser]:
        """Возвращает всех известных пользователей реестра."""

        with self._lock:
            data = self._load()
            result: list[RegisteredUser] = []
            known_ids: set[int] = set()
            for raw_user_id, item in data["users"].items():
                try:
                    user_id = int(raw_user_id)
                except ValueError:
                    continue
                known_ids.add(user_id)
                role = self._normalize_role(str(item.get("role", "user"))) or "user"
                phone = item.get("phone")
                phone_value = str(phone) if phone else None
                result.append(
                    RegisteredUser(
                        user_id=user_id,
                        user_name=str(item.get("user_name", f"ID {user_id}")),
                        phone=phone_value,
                        hotel_code=self._normalize_hotel(str(item.get("hotel_code", "") or "")),
                        role=role,
                        status=str(item.get("status", "active")),
                        created_at=str(item.get("created_at", "-")),
                        updated_at=str(item.get("updated_at", "-")),
                    )
                )
            for value in data["approved"]:
                try:
                    user_id = int(value)
                except ValueError:
                    continue
                if user_id in known_ids:
                    continue
                result.append(
                    RegisteredUser(
                        user_id=user_id,
                        user_name=f"ID {user_id}",
                        phone=None,
                        hotel_code=None,
                        role="user",
                        status="active",
                        created_at="-",
                        updated_at="-",
                    )
                )
            result.sort(key=lambda x: (x.status, x.user_id))
            return result

    def get_ids_by_role(self, role: str) -> tuple[int, ...]:
        normalized_role = self._normalize_role(role)
        if not normalized_role:
            return ()
        with self._lock:
            data = self._load()
            ids: set[int] = set()
            for raw_user_id, item in data["users"].items():
                try:
                    user_id = int(raw_user_id)
                except ValueError:
                    continue
                current_role = self._normalize_role(str(item.get("role", "user"))) or "user"
                status = str(item.get("status", "active"))
                if status == "active" and current_role == normalized_role:
                    ids.add(user_id)
            if normalized_role == "user":
                for value in data["approved"]:
                    try:
                        user_id = int(value)
                    except ValueError:
                        continue
                    if str(user_id) not in data["users"]:
                        ids.add(user_id)
            return tuple(sorted(ids))

    def ban(self, user_id: int) -> str:
        with self._lock:
            data = self._load()
            key = str(user_id)
            user_data = data["users"].get(key)
            if not user_data and user_id in set(int(value) for value in data["approved"]):
                now = datetime.now(timezone.utc).isoformat()
                data["users"][key] = {
                    "user_name": f"ID {user_id}",
                    "phone": None,
                    "hotel_code": None,
                    "role": "user",
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                }
                user_data = data["users"].get(key)
            if not user_data:
                return "not_found"
            if str(user_data.get("status", "active")) == "banned":
                return "already_banned"
            user_data["status"] = "banned"
            user_data["updated_at"] = datetime.now(timezone.utc).isoformat()
            approved = set(int(value) for value in data["approved"])
            if user_id in approved:
                approved.discard(user_id)
                data["approved"] = sorted(approved)
            self._save(data)
            return "banned"

    def delete_user(self, user_id: int) -> str:
        with self._lock:
            data = self._load()
            key = str(user_id)
            found = False
            if key in data["users"]:
                data["users"].pop(key, None)
                found = True
            if key in data["pending"]:
                data["pending"].pop(key, None)
                found = True
            approved = set(int(value) for value in data["approved"])
            if user_id in approved:
                approved.discard(user_id)
                data["approved"] = sorted(approved)
                found = True
            if not found:
                return "not_found"
            self._save(data)
            return "deleted"

    def get_user_hotel(self, user_id: int) -> str | None:
        with self._lock:
            data = self._load()
            item = data["users"].get(str(user_id))
            if not item:
                return None
            return self._normalize_hotel(str(item.get("hotel_code", "") or ""))

    def set_user_hotel(self, user_id: int, hotel_code: str | None) -> str:
        with self._lock:
            raw_hotel = str(hotel_code or "").strip()
            normalized_hotel = self._normalize_hotel(raw_hotel)
            if raw_hotel and raw_hotel.lower() not in {"none", "-", "null"} and not normalized_hotel:
                return "invalid_hotel"

            data = self._load()
            key = str(user_id)
            user_data = data["users"].get(key)
            if not user_data:
                return "not_found"

            current_hotel = self._normalize_hotel(str(user_data.get("hotel_code", "") or ""))
            if current_hotel == normalized_hotel:
                return "no_change"

            user_data["hotel_code"] = normalized_hotel
            user_data["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save(data)
            return "updated"

    @staticmethod
    def list_hotels() -> tuple[tuple[str, str], ...]:
        return tuple((code, HOTEL_LABELS[code]) for code in HOTEL_LABELS)

    @staticmethod
    def get_hotel_label(hotel_code: str | None) -> str | None:
        normalized = UserAccessRegistry._normalize_hotel(hotel_code or "")
        if not normalized:
            return None
        return HOTEL_LABELS.get(normalized)

    @staticmethod
    def get_hotel_features(hotel_code: str | None) -> tuple[str, ...]:
        normalized = UserAccessRegistry._normalize_hotel(hotel_code or "")
        if not normalized:
            return ()
        return HOTEL_FEATURES.get(normalized, ())

    def list_pending(self) -> list[PendingAccessRequest]:
        with self._lock:
            data = self._load()
            result: list[PendingAccessRequest] = []
            for raw_user_id, item in data["pending"].items():
                user_id = int(raw_user_id)
                user_name = str(item.get("user_name", "unknown"))
                phone = item.get("phone")
                phone_value = str(phone) if phone else None
                requested_at = str(item.get("requested_at", "-"))
                result.append(
                    PendingAccessRequest(
                        user_id=user_id,
                        user_name=user_name,
                        phone=phone_value,
                        requested_at=requested_at,
                    )
                )
            result.sort(key=lambda x: x.requested_at)
            return result

    @staticmethod
    def _normalize_role(role: str) -> str | None:
        raw = (role or "").strip().lower()
        if raw in {"user", "usr"}:
            return "user"
        if raw in {"it", "it specialist", "specialist", "it_specialist"}:
            return "IT specialist"
        if raw in {"admin", "administrator"}:
            return "admin"
        return None

    @staticmethod
    def _normalize_hotel(hotel_code: str) -> str | None:
        raw = (hotel_code or "").strip().lower()
        if raw in {"", "none", "-", "null"}:
            return None
        if raw in {"jamaika", "джамайка"}:
            return "jamaica"
        if raw in {"oldanapa", "old-anapa", "старинная анапа"}:
            return "old_anapa"
        if raw in HOTEL_LABELS:
            return raw
        return None
