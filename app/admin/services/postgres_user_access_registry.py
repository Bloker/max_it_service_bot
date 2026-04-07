import threading
from datetime import datetime, timezone

from app.admin.services.user_access_registry import PendingAccessRequest, RegisteredUser

HOTEL_LABELS: dict[str, str] = {
    "jamaica": "Отель Джамайка",
    "old_anapa": "Отель Старинная Анапа",
}
HOTEL_FEATURES: dict[str, tuple[str, ...]] = {
    "jamaica": ("wifi_guest_issue", "tv_guest_issue"),
    "old_anapa": ("wifi_guest_issue",),
}

_ROLE_CODE_TO_DISPLAY = {
    "user": "user",
    "it_specialist": "IT specialist",
    "admin": "admin",
}
_ROLE_DISPLAY_TO_CODE = {value: key for key, value in _ROLE_CODE_TO_DISPLAY.items()}


class PostgresUserAccessRegistry:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        sslmode: str = "prefer",
        connect_timeout_sec: int = 5,
    ) -> None:
        self._conninfo = (
            f"host={host} port={port} dbname={database} user={user} "
            f"password={password} sslmode={sslmode} connect_timeout={connect_timeout_sec}"
        )
        self._lock = threading.Lock()

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL registry requires psycopg. Install dependencies from requirements.txt"
            ) from exc
        return psycopg.connect(self._conninfo, row_factory=dict_row)

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

    @staticmethod
    def _to_role_code(role_display: str) -> str:
        return _ROLE_DISPLAY_TO_CODE.get(role_display, "user")

    @staticmethod
    def _to_role_display(role_code: str | None) -> str:
        return _ROLE_CODE_TO_DISPLAY.get((role_code or "").strip().lower(), "user")

    def get_approved_ids(self) -> tuple[int, ...]:
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT external_user_id
                    FROM auth.users
                    WHERE status = 'active'
                    ORDER BY external_user_id
                    """
                )
                rows = cur.fetchall()
        return tuple(int(row["external_user_id"]) for row in rows)

    def get_banned_ids(self) -> tuple[int, ...]:
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT external_user_id
                    FROM auth.users
                    WHERE status = 'banned'
                    ORDER BY external_user_id
                    """
                )
                rows = cur.fetchall()
        return tuple(int(row["external_user_id"]) for row in rows)

    def is_approved(self, user_id: int) -> bool:
        return user_id in set(self.get_approved_ids())

    def request_access(self, user_id: int, user_name: str, phone: str | None = None) -> str:
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT status
                    FROM auth.users
                    WHERE external_user_id = %s
                    """,
                    (user_id,),
                )
                existing = cur.fetchone()
                if existing and str(existing["status"]) == "active":
                    conn.commit()
                    return "already_approved"

                cur.execute(
                    """
                    SELECT 1
                    FROM auth.access_requests
                    WHERE external_user_id = %s AND status = 'pending'
                    LIMIT 1
                    """,
                    (user_id,),
                )
                if cur.fetchone() is not None:
                    conn.commit()
                    return "already_pending"

                cur.execute(
                    """
                    INSERT INTO auth.access_requests(
                        external_user_id, requested_name, requested_phone, status, requested_at
                    )
                    VALUES (%s, %s, %s, 'pending', %s)
                    """,
                    (user_id, user_name, phone, datetime.now(tz=timezone.utc)),
                )
            conn.commit()
        return "created"

    def approve(self, user_id: int, role: str = "user") -> str:
        normalized_role = self._normalize_role(role)
        if not normalized_role:
            return "invalid_role"
        role_code = self._to_role_code(normalized_role)

        with self._lock, self._connect() as conn:
            now = datetime.now(tz=timezone.utc)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, status
                    FROM auth.users
                    WHERE external_user_id = %s
                    FOR UPDATE
                    """,
                    (user_id,),
                )
                user_row = cur.fetchone()
                if user_row and str(user_row["status"]) == "active":
                    conn.commit()
                    return "already_approved"

                cur.execute(
                    """
                    SELECT id, requested_name, requested_phone, requested_at
                    FROM auth.access_requests
                    WHERE external_user_id = %s AND status = 'pending'
                    ORDER BY requested_at DESC
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (user_id,),
                )
                pending = cur.fetchone()
                if pending is None:
                    conn.commit()
                    return "not_found"

                user_name = str(pending.get("requested_name") or f"ID {user_id}")
                phone = pending.get("requested_phone")
                created_at = pending.get("requested_at") or now

                cur.execute(
                    """
                    INSERT INTO auth.users(
                        external_user_id, display_name, phone, status, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, 'active', %s, %s)
                    ON CONFLICT (external_user_id) DO UPDATE
                    SET
                        display_name = COALESCE(EXCLUDED.display_name, auth.users.display_name),
                        phone = COALESCE(EXCLUDED.phone, auth.users.phone),
                        status = 'active',
                        updated_at = EXCLUDED.updated_at
                    RETURNING id
                    """,
                    (user_id, user_name, phone, created_at, now),
                )
                db_user = cur.fetchone()
                if db_user is None:
                    conn.rollback()
                    return "not_found"
                internal_user_id = int(db_user["id"])

                cur.execute("SELECT id FROM auth.roles WHERE code = %s", (role_code,))
                role_row = cur.fetchone()
                if role_row is None:
                    conn.rollback()
                    return "invalid_role"
                role_id = int(role_row["id"])

                cur.execute(
                    """
                    UPDATE auth.user_roles
                    SET valid_to = %s
                    WHERE user_id = %s AND valid_to IS NULL AND role_id <> %s
                    """,
                    (now, internal_user_id, role_id),
                )
                cur.execute(
                    """
                    SELECT 1
                    FROM auth.user_roles
                    WHERE user_id = %s AND role_id = %s AND valid_to IS NULL
                    """,
                    (internal_user_id, role_id),
                )
                if cur.fetchone() is None:
                    cur.execute(
                        """
                        INSERT INTO auth.user_roles(user_id, role_id, valid_from, valid_to)
                        VALUES (%s, %s, %s, NULL)
                        """,
                        (internal_user_id, role_id, now),
                    )

                cur.execute(
                    """
                    UPDATE auth.access_requests
                    SET status = 'approved', processed_at = %s
                    WHERE external_user_id = %s AND status = 'pending'
                    """,
                    (now, user_id),
                )
            conn.commit()
        return "approved"

    def reject(self, user_id: int) -> str:
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE auth.access_requests
                    SET status = 'rejected', processed_at = %s
                    WHERE external_user_id = %s AND status = 'pending'
                    """,
                    (datetime.now(tz=timezone.utc), user_id),
                )
                updated = cur.rowcount
            conn.commit()
        return "rejected" if updated > 0 else "not_found"

    def list_users(self) -> list[RegisteredUser]:
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        u.external_user_id,
                        COALESCE(u.display_name, ('ID ' || u.external_user_id::text)) AS user_name,
                        u.phone,
                        u.status,
                        u.created_at,
                        u.updated_at,
                        role_map.role_code,
                        hotel_map.hotel_code
                    FROM auth.users u
                    LEFT JOIN LATERAL (
                        SELECT r.code AS role_code
                        FROM auth.user_roles ur
                        JOIN auth.roles r ON r.id = ur.role_id
                        WHERE ur.user_id = u.id AND ur.valid_to IS NULL
                        ORDER BY ur.valid_from DESC
                        LIMIT 1
                    ) role_map ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT h.code AS hotel_code
                        FROM auth.user_hotel_memberships hm
                        JOIN auth.hotels h ON h.id = hm.hotel_id
                        WHERE hm.user_id = u.id AND hm.valid_to IS NULL
                        ORDER BY hm.valid_from DESC
                        LIMIT 1
                    ) hotel_map ON TRUE
                    ORDER BY u.status, u.external_user_id
                    """
                )
                rows = cur.fetchall()

        result: list[RegisteredUser] = []
        for row in rows:
            role_display = self._to_role_display(row.get("role_code"))
            result.append(
                RegisteredUser(
                    user_id=int(row["external_user_id"]),
                    user_name=str(row["user_name"]),
                    phone=str(row["phone"]) if row.get("phone") else None,
                    hotel_code=self._normalize_hotel(str(row.get("hotel_code") or "")),
                    role=role_display,
                    status=str(row["status"]),
                    created_at=str(row["created_at"]),
                    updated_at=str(row["updated_at"]),
                )
            )
        return result

    def get_ids_by_role(self, role: str) -> tuple[int, ...]:
        normalized = self._normalize_role(role)
        if not normalized:
            return ()
        role_code = self._to_role_code(normalized)

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                if role_code == "user":
                    cur.execute(
                        """
                        SELECT DISTINCT u.external_user_id
                        FROM auth.users u
                        LEFT JOIN LATERAL (
                            SELECT r.code AS role_code
                            FROM auth.user_roles ur
                            JOIN auth.roles r ON r.id = ur.role_id
                            WHERE ur.user_id = u.id AND ur.valid_to IS NULL
                            ORDER BY ur.valid_from DESC
                            LIMIT 1
                        ) role_map ON TRUE
                        WHERE u.status = 'active'
                          AND (role_map.role_code = 'user' OR role_map.role_code IS NULL)
                        ORDER BY u.external_user_id
                        """
                    )
                else:
                    cur.execute(
                        """
                        SELECT DISTINCT u.external_user_id
                        FROM auth.users u
                        JOIN auth.user_roles ur ON ur.user_id = u.id AND ur.valid_to IS NULL
                        JOIN auth.roles r ON r.id = ur.role_id
                        WHERE u.status = 'active' AND r.code = %s
                        ORDER BY u.external_user_id
                        """,
                        (role_code,),
                    )
                rows = cur.fetchall()
        return tuple(int(row["external_user_id"]) for row in rows)

    def ban(self, user_id: int) -> str:
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT status
                    FROM auth.users
                    WHERE external_user_id = %s
                    FOR UPDATE
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                if row is None:
                    conn.commit()
                    return "not_found"
                if str(row["status"]) == "banned":
                    conn.commit()
                    return "already_banned"

                now = datetime.now(tz=timezone.utc)
                cur.execute(
                    """
                    UPDATE auth.users
                    SET status = 'banned', updated_at = %s
                    WHERE external_user_id = %s
                    """,
                    (now, user_id),
                )
                cur.execute(
                    """
                    UPDATE auth.access_requests
                    SET status = 'rejected', processed_at = %s, rejection_reason = 'banned'
                    WHERE external_user_id = %s AND status = 'pending'
                    """,
                    (now, user_id),
                )
            conn.commit()
        return "banned"

    def delete_user(self, user_id: int) -> str:
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM auth.users WHERE external_user_id = %s",
                    (user_id,),
                )
                deleted_user = cur.rowcount
                cur.execute(
                    "DELETE FROM auth.access_requests WHERE external_user_id = %s",
                    (user_id,),
                )
                deleted_requests = cur.rowcount
            conn.commit()
        return "deleted" if (deleted_user > 0 or deleted_requests > 0) else "not_found"

    def get_user_hotel(self, user_id: int) -> str | None:
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT h.code
                    FROM auth.users u
                    LEFT JOIN auth.user_hotel_memberships hm
                      ON hm.user_id = u.id AND hm.valid_to IS NULL
                    LEFT JOIN auth.hotels h ON h.id = hm.hotel_id
                    WHERE u.external_user_id = %s
                    ORDER BY hm.valid_from DESC NULLS LAST
                    LIMIT 1
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        return self._normalize_hotel(str(row.get("code") or ""))

    def set_user_hotel(self, user_id: int, hotel_code: str | None) -> str:
        raw_hotel = str(hotel_code or "").strip()
        normalized_hotel = self._normalize_hotel(raw_hotel)
        if raw_hotel and raw_hotel.lower() not in {"none", "-", "null"} and not normalized_hotel:
            return "invalid_hotel"

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id
                    FROM auth.users
                    WHERE external_user_id = %s
                    FOR UPDATE
                    """,
                    (user_id,),
                )
                user_row = cur.fetchone()
                if user_row is None:
                    conn.commit()
                    return "not_found"
                internal_user_id = int(user_row["id"])

                cur.execute(
                    """
                    SELECT h.code AS current_hotel
                    FROM auth.user_hotel_memberships hm
                    JOIN auth.hotels h ON h.id = hm.hotel_id
                    WHERE hm.user_id = %s AND hm.valid_to IS NULL
                    ORDER BY hm.valid_from DESC
                    LIMIT 1
                    """,
                    (internal_user_id,),
                )
                hotel_row = cur.fetchone()
                current_hotel = self._normalize_hotel(str((hotel_row or {}).get("current_hotel") or ""))
                if current_hotel == normalized_hotel:
                    conn.commit()
                    return "no_change"

                now = datetime.now(tz=timezone.utc)
                cur.execute(
                    """
                    UPDATE auth.user_hotel_memberships
                    SET valid_to = %s
                    WHERE user_id = %s AND valid_to IS NULL
                    """,
                    (now, internal_user_id),
                )
                if normalized_hotel is not None:
                    cur.execute("SELECT id FROM auth.hotels WHERE code = %s", (normalized_hotel,))
                    hotel_row = cur.fetchone()
                    if hotel_row is None:
                        conn.rollback()
                        return "invalid_hotel"
                    hotel_id = int(hotel_row["id"])
                    cur.execute(
                        """
                        INSERT INTO auth.user_hotel_memberships(user_id, hotel_id, valid_from, valid_to)
                        VALUES (%s, %s, %s, NULL)
                        """,
                        (internal_user_id, hotel_id, now),
                    )
                cur.execute(
                    "UPDATE auth.users SET updated_at = %s WHERE id = %s",
                    (now, internal_user_id),
                )
            conn.commit()
        return "updated"

    @staticmethod
    def list_hotels() -> tuple[tuple[str, str], ...]:
        return tuple((code, HOTEL_LABELS[code]) for code in HOTEL_LABELS)

    @staticmethod
    def get_hotel_label(hotel_code: str | None) -> str | None:
        normalized = PostgresUserAccessRegistry._normalize_hotel(hotel_code or "")
        if not normalized:
            return None
        return HOTEL_LABELS.get(normalized)

    @staticmethod
    def get_hotel_features(hotel_code: str | None) -> tuple[str, ...]:
        normalized = PostgresUserAccessRegistry._normalize_hotel(hotel_code or "")
        if not normalized:
            return ()
        return HOTEL_FEATURES.get(normalized, ())

    def list_pending(self) -> list[PendingAccessRequest]:
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT external_user_id, requested_name, requested_phone, requested_at
                    FROM auth.access_requests
                    WHERE status = 'pending'
                    ORDER BY requested_at
                    """
                )
                rows = cur.fetchall()
        return [
            PendingAccessRequest(
                user_id=int(row["external_user_id"]),
                user_name=str(row.get("requested_name") or f"ID {int(row['external_user_id'])}"),
                phone=str(row["requested_phone"]) if row.get("requested_phone") else None,
                requested_at=str(row["requested_at"]),
            )
            for row in rows
        ]
