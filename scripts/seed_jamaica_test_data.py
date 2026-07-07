"""Seed test_dev_max справочниками Джамайки для будущего room-ticket flow."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from psycopg.rows import dict_row

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.helpdesk.services.jamaica_seed_data import (  # noqa: E402
    JAMAICA_HOTEL_CODE,
    JAMAICA_HOTEL_NAME,
    JAMAICA_ISSUE_CATEGORIES,
    build_jamaica_locations,
)
from app.infrastructure.database.psycopg_connection import connect_postgres  # noqa: E402
from config.config import get_config  # noqa: E402


def main() -> None:
    args = _parse_args()
    if args.dry_run_json:
        _print_dry_run_json()
        return

    if args.db:
        os.environ["MAX_TICKET_PG_DB"] = args.db

    cfg = get_config()
    if cfg.tickets.backend != "postgres":
        raise RuntimeError("Set MAX_TICKET_BACKEND=postgres before seed")
    database = cfg.tickets.postgres_db
    if database != "test_dev_max" and not args.allow_non_test:
        raise RuntimeError(
            "Refusing to seed non-test database. Use --db test_dev_max "
            "or pass --allow-non-test explicitly."
        )

    conninfo = (
        f"host={cfg.tickets.postgres_host} "
        f"port={cfg.tickets.postgres_port} "
        f"dbname={database} "
        f"user={cfg.tickets.postgres_user} "
        f"password={cfg.tickets.postgres_password} "
        f"sslmode={cfg.tickets.postgres_sslmode} "
        f"connect_timeout={cfg.tickets.postgres_connect_timeout_sec}"
    )
    summary = seed_jamaica(conninfo)
    print(
        "Jamaica seed complete: "
        f"database={database} hotel_id={summary['hotel_id']} "
        f"locations={summary['locations']} categories={summary['categories']} "
        f"memberships_added={summary['memberships_added']}"
    )


def seed_jamaica(conninfo: str) -> dict[str, int]:
    """Идемпотентно создает/обновляет отель, категории и locations."""

    locations = build_jamaica_locations()
    with connect_postgres(conninfo, row_factory=dict_row, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auth.hotels(code, name, is_active)
                VALUES (%s, %s, TRUE)
                ON CONFLICT (code)
                DO UPDATE SET name = EXCLUDED.name, is_active = TRUE
                RETURNING id
                """,
                (JAMAICA_HOTEL_CODE, JAMAICA_HOTEL_NAME),
            )
            hotel_id = int(cur.fetchone()["id"])

            category_ids: dict[str, int] = {}
            for category in JAMAICA_ISSUE_CATEGORIES:
                cur.execute(
                    """
                    INSERT INTO helpdesk.issue_categories(
                        code, title, requires_location, is_active, sort_order
                    )
                    VALUES (%s, %s, TRUE, TRUE, %s)
                    ON CONFLICT (code)
                    DO UPDATE SET
                        title = EXCLUDED.title,
                        requires_location = TRUE,
                        is_active = TRUE,
                        sort_order = EXCLUDED.sort_order,
                        updated_at = NOW()
                    RETURNING id
                    """,
                    (category.code, category.title, category.sort_order),
                )
                category_id = int(cur.fetchone()["id"])
                category_ids[category.code] = category_id
                cur.execute(
                    """
                    INSERT INTO helpdesk.hotel_issue_categories(
                        hotel_id, category_id, is_enabled, sort_order
                    )
                    VALUES (%s, %s, TRUE, %s)
                    ON CONFLICT (hotel_id, category_id)
                    DO UPDATE SET
                        is_enabled = TRUE,
                        sort_order = EXCLUDED.sort_order
                    """,
                    (hotel_id, category_id, category.sort_order),
                )

            for location in locations:
                cur.execute(
                    """
                    INSERT INTO helpdesk.locations(
                        hotel_id, location_code, location_type, building_name,
                        room_number, display_name, is_active, sort_order
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s)
                    ON CONFLICT (hotel_id, room_number)
                    DO UPDATE SET
                        location_code = EXCLUDED.location_code,
                        location_type = EXCLUDED.location_type,
                        building_name = EXCLUDED.building_name,
                        display_name = EXCLUDED.display_name,
                        is_active = TRUE,
                        sort_order = EXCLUDED.sort_order,
                        updated_at = NOW()
                    """,
                    (
                        hotel_id,
                        location.location_code,
                        location.location_type,
                        location.building_name,
                        location.room_number,
                        location.display_name,
                        location.sort_order,
                    ),
                )
            cur.execute(
                """
                INSERT INTO auth.user_hotel_memberships(user_id, hotel_id, valid_from, valid_to)
                SELECT u.id, %s, NOW(), NULL
                FROM auth.users u
                WHERE u.status = 'active'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM auth.user_hotel_memberships hm
                      WHERE hm.user_id = u.id AND hm.valid_to IS NULL
                  )
                """,
                (hotel_id,),
            )
            memberships_added = cur.rowcount
        conn.commit()
    return {
        "hotel_id": hotel_id,
        "locations": len(locations),
        "categories": len(category_ids),
        "memberships_added": memberships_added,
    }


def _print_dry_run_json() -> None:
    locations = build_jamaica_locations()
    payload = {
        "hotel_code": JAMAICA_HOTEL_CODE,
        "locations": [asdict(location) for location in locations],
        "categories": [asdict(category) for category in JAMAICA_ISSUE_CATEGORIES],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Override MAX_TICKET_PG_DB")
    parser.add_argument(
        "--allow-non-test",
        action="store_true",
        help="Allow seeding a database other than test_dev_max",
    )
    parser.add_argument(
        "--dry-run-json",
        action="store_true",
        help="Print generated seed data as JSON without DB connection",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
