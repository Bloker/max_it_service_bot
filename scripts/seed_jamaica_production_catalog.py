"""Создает production-safe каталог Джамайки без рабочих данных и статей БЗ."""

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
    JAMAICA_KNOWLEDGE_SCOPES,
    build_jamaica_locations,
)
from app.infrastructure.database.psycopg_connection import connect_postgres  # noqa: E402
from config.config import get_config  # noqa: E402


def main() -> None:
    """Запускает явный production-safe seed каталога."""

    args = _parse_args()
    if args.dry_run_json:
        _print_dry_run_json()
        return
    if not args.allow_production:
        raise RuntimeError(
            "Refusing to write catalog data without --allow-production. "
            "This seed must never be used for test articles or ticket data."
        )
    if args.db:
        os.environ["MAX_TICKET_PG_DB"] = args.db

    cfg = get_config()
    if cfg.tickets.backend != "postgres":
        raise RuntimeError("Set MAX_TICKET_BACKEND=postgres before seed")

    database = cfg.tickets.postgres_db
    conninfo = (
        f"host={cfg.tickets.postgres_host} "
        f"port={cfg.tickets.postgres_port} "
        f"dbname={database} "
        f"user={cfg.tickets.postgres_user} "
        f"password={cfg.tickets.postgres_password} "
        f"sslmode={cfg.tickets.postgres_sslmode} "
        f"connect_timeout={cfg.tickets.postgres_connect_timeout_sec}"
    )
    summary = seed_jamaica_production_catalog(conninfo)
    print(
        "Jamaica production catalog seed complete: "
        f"database={database} hotel_id={summary['hotel_id']} "
        f"locations={summary['locations']} categories={summary['categories']} "
        f"scopes={summary['scopes']}"
    )


def seed_jamaica_production_catalog(conninfo: str) -> dict[str, int]:
    """Идемпотентно создает только каталог Джамайки и разделы БЗ."""

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

            category_ids = _upsert_categories(cur, hotel_id)
            _upsert_locations(cur, hotel_id, locations)
            _upsert_scopes(cur, hotel_id)
        conn.commit()

    return {
        "hotel_id": hotel_id,
        "locations": len(locations),
        "categories": len(category_ids),
        "scopes": len(JAMAICA_KNOWLEDGE_SCOPES),
    }


def _upsert_categories(cur, hotel_id: int) -> dict[str, int]:
    """Создает категории и включает их только для Джамайки."""

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
    return category_ids


def _upsert_locations(cur, hotel_id: int, locations) -> None:
    """Создает номера и домики Джамайки, не затрагивая заявки и контекст."""

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


def _upsert_scopes(cur, hotel_id: int) -> None:
    """Создает разделы БЗ, но намеренно не создает ни одной статьи."""

    for code, title, scope_type, sort_order in JAMAICA_KNOWLEDGE_SCOPES:
        current_hotel_id = hotel_id if code == "jamaica" else None
        cur.execute(
            """
            INSERT INTO helpdesk.knowledge_scopes(
                code, title, scope_type, hotel_id, is_active, sort_order
            )
            VALUES (%s, %s, %s, %s, TRUE, %s)
            ON CONFLICT (code) DO UPDATE
            SET title = EXCLUDED.title,
                scope_type = EXCLUDED.scope_type,
                hotel_id = EXCLUDED.hotel_id,
                is_active = TRUE,
                sort_order = EXCLUDED.sort_order,
                updated_at = NOW()
            """,
            (code, title, scope_type, current_hotel_id, sort_order),
        )


def _print_dry_run_json() -> None:
    """Печатает только статический каталог без подключения к БД."""

    print(
        json.dumps(
            {
                "hotel_code": JAMAICA_HOTEL_CODE,
                "locations": [asdict(location) for location in build_jamaica_locations()],
                "categories": [asdict(category) for category in JAMAICA_ISSUE_CATEGORIES],
                "knowledge_scopes": [
                    {
                        "code": code,
                        "title": title,
                        "scope_type": scope_type,
                        "sort_order": sort_order,
                    }
                    for code, title, scope_type, sort_order in JAMAICA_KNOWLEDGE_SCOPES
                ],
                "creates": [
                    "auth.hotels",
                    "helpdesk.issue_categories",
                    "helpdesk.hotel_issue_categories",
                    "helpdesk.locations",
                    "helpdesk.knowledge_scopes",
                ],
                "does_not_create": [
                    "helpdesk.knowledge_articles",
                    "helpdesk.ticket_comments",
                    "helpdesk.media_attachments",
                    "helpdesk.ticket_context",
                    "public.helpdesk_tickets",
                    "helpdesk.tickets",
                    "integration.message_links",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Override MAX_TICKET_PG_DB")
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="Explicitly allow catalog writes to the selected database",
    )
    parser.add_argument(
        "--dry-run-json",
        action="store_true",
        help="Print the catalog without connecting to PostgreSQL",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
