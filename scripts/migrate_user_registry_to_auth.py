import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import psycopg

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import get_config


ROLE_MAP = {
    "user": "user",
    "it specialist": "it_specialist",
    "it_specialist": "it_specialist",
    "it": "it_specialist",
    "admin": "admin",
    "administrator": "admin",
}


def _normalize_role(raw: str | None) -> str:
    key = (raw or "").strip().lower()
    return ROLE_MAP.get(key, "user")


def _resolve_registry_path(path_raw: str) -> Path:
    path = Path(path_raw)
    if path.is_absolute():
        return path
    return ROOT_DIR / path


def _upsert_user(
    cur,
    *,
    external_user_id: int,
    display_name: str | None,
    phone: str | None,
    status: str,
    created_at: datetime,
    updated_at: datetime,
) -> int:
    cur.execute(
        """
        INSERT INTO auth.users(external_user_id, display_name, phone, status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (external_user_id) DO UPDATE
        SET
            display_name = COALESCE(EXCLUDED.display_name, auth.users.display_name),
            phone = COALESCE(EXCLUDED.phone, auth.users.phone),
            status = EXCLUDED.status,
            updated_at = EXCLUDED.updated_at
        RETURNING id
        """,
        (external_user_id, display_name, phone, status, created_at, updated_at),
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"Failed to upsert user {external_user_id}")
    return int(row["id"])


def _ensure_active_role(cur, *, internal_user_id: int, role_code: str) -> None:
    cur.execute("SELECT id FROM auth.roles WHERE code = %s", (role_code,))
    role = cur.fetchone()
    if role is None:
        return
    role_id = int(role["id"])
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
            VALUES (%s, %s, NOW(), NULL)
            """,
            (internal_user_id, role_id),
        )


def _set_hotel_membership(cur, *, internal_user_id: int, hotel_code: str | None) -> None:
    if not hotel_code:
        cur.execute(
            """
            UPDATE auth.user_hotel_memberships
            SET valid_to = NOW()
            WHERE user_id = %s AND valid_to IS NULL
            """,
            (internal_user_id,),
        )
        return

    cur.execute("SELECT id FROM auth.hotels WHERE code = %s", (hotel_code,))
    hotel = cur.fetchone()
    if hotel is None:
        return
    hotel_id = int(hotel["id"])

    cur.execute(
        """
        UPDATE auth.user_hotel_memberships
        SET valid_to = NOW()
        WHERE user_id = %s AND valid_to IS NULL AND hotel_id <> %s
        """,
        (internal_user_id, hotel_id),
    )
    cur.execute(
        """
        SELECT 1
        FROM auth.user_hotel_memberships
        WHERE user_id = %s AND hotel_id = %s AND valid_to IS NULL
        """,
        (internal_user_id, hotel_id),
    )
    if cur.fetchone() is None:
        cur.execute(
            """
            INSERT INTO auth.user_hotel_memberships(user_id, hotel_id, valid_from, valid_to)
            VALUES (%s, %s, NOW(), NULL)
            """,
            (internal_user_id, hotel_id),
        )


def main() -> None:
    cfg = get_config()
    if cfg.tickets.backend != "postgres":
        raise RuntimeError("Set MAX_TICKET_BACKEND=postgres before auth migration")

    registry_path = _resolve_registry_path(cfg.bot.user_registry_path)
    if not registry_path.exists():
        raise RuntimeError(f"Registry file not found: {registry_path}")

    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    users = payload.get("users", {})
    approved = payload.get("approved", [])
    pending = payload.get("pending", {})

    conninfo = (
        f"host={cfg.tickets.postgres_host} "
        f"port={cfg.tickets.postgres_port} "
        f"dbname={cfg.tickets.postgres_db} "
        f"user={cfg.tickets.postgres_user} "
        f"password={cfg.tickets.postgres_password} "
        f"sslmode={cfg.tickets.postgres_sslmode} "
        f"connect_timeout={cfg.tickets.postgres_connect_timeout_sec}"
    )

    migrated_users = 0
    migrated_pending = 0
    now = datetime.now(tz=timezone.utc)

    with psycopg.connect(conninfo, autocommit=False) as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            for raw_user_id, item in users.items():
                try:
                    external_user_id = int(raw_user_id)
                except Exception:
                    continue

                display_name = str(item.get("user_name") or f"ID {external_user_id}")
                phone = item.get("phone")
                status = str(item.get("status") or "active")
                if status not in {"active", "banned"}:
                    status = "active"

                created_at_raw = item.get("created_at")
                updated_at_raw = item.get("updated_at")
                try:
                    created_at = (
                        datetime.fromisoformat(str(created_at_raw))
                        if created_at_raw
                        else now
                    )
                except Exception:
                    created_at = now
                try:
                    updated_at = (
                        datetime.fromisoformat(str(updated_at_raw))
                        if updated_at_raw
                        else now
                    )
                except Exception:
                    updated_at = now

                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)

                internal_user_id = _upsert_user(
                    cur,
                    external_user_id=external_user_id,
                    display_name=display_name,
                    phone=str(phone) if phone else None,
                    status=status,
                    created_at=created_at,
                    updated_at=updated_at,
                )

                role_code = _normalize_role(str(item.get("role") or "user"))
                _ensure_active_role(cur, internal_user_id=internal_user_id, role_code=role_code)

                hotel_code = str(item.get("hotel_code") or "").strip().lower() or None
                _set_hotel_membership(cur, internal_user_id=internal_user_id, hotel_code=hotel_code)
                migrated_users += 1

            for raw in approved:
                try:
                    external_user_id = int(raw)
                except Exception:
                    continue
                cur.execute(
                    "SELECT id FROM auth.users WHERE external_user_id = %s",
                    (external_user_id,),
                )
                row = cur.fetchone()
                if row is None:
                    internal_user_id = _upsert_user(
                        cur,
                        external_user_id=external_user_id,
                        display_name=f"ID {external_user_id}",
                        phone=None,
                        status="active",
                        created_at=now,
                        updated_at=now,
                    )
                else:
                    internal_user_id = int(row["id"])
                _ensure_active_role(cur, internal_user_id=internal_user_id, role_code="user")

            for raw_user_id, item in pending.items():
                try:
                    external_user_id = int(raw_user_id)
                except Exception:
                    continue
                requested_name = item.get("user_name")
                requested_phone = item.get("phone")
                requested_at_raw = item.get("requested_at")
                try:
                    requested_at = (
                        datetime.fromisoformat(str(requested_at_raw))
                        if requested_at_raw
                        else now
                    )
                except Exception:
                    requested_at = now
                if requested_at.tzinfo is None:
                    requested_at = requested_at.replace(tzinfo=timezone.utc)

                cur.execute(
                    """
                    INSERT INTO auth.access_requests(
                        external_user_id, requested_name, requested_phone, status, requested_at
                    )
                    VALUES (%s, %s, %s, 'pending', %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (external_user_id, requested_name, requested_phone, requested_at),
                )
                migrated_pending += 1

        conn.commit()

    print(f"Registry migrated from: {registry_path}")
    print(f"Users processed: {migrated_users}")
    print(f"Pending requests processed: {migrated_pending}")


if __name__ == "__main__":
    main()
