"""Read-only сверка legacy и normalized схем заявок."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

import psycopg
from psycopg.rows import dict_row


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import get_config


def main() -> None:
    """Печатает отчет сверки `public.helpdesk_tickets` и `helpdesk.tickets`."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Временно переопределить MAX_TICKET_PG_DB")
    args = parser.parse_args()

    if args.db:
        os.environ["MAX_TICKET_PG_DB"] = args.db

    cfg = get_config()
    if cfg.tickets.backend != "postgres":
        raise RuntimeError("Set MAX_TICKET_BACKEND=postgres before reconciliation")

    conninfo = (
        f"host={cfg.tickets.postgres_host} "
        f"port={cfg.tickets.postgres_port} "
        f"dbname={cfg.tickets.postgres_db} "
        f"user={cfg.tickets.postgres_user} "
        f"password={cfg.tickets.postgres_password} "
        f"sslmode={cfg.tickets.postgres_sslmode} "
        f"connect_timeout={cfg.tickets.postgres_connect_timeout_sec}"
    )

    with psycopg.connect(conninfo, row_factory=dict_row) as conn:
        conn.execute("BEGIN READ ONLY")
        try:
            report = _collect_report(conn)
        finally:
            conn.execute("ROLLBACK")

    print(f"database={cfg.tickets.postgres_db}")
    for key, value in report.items():
        print(f"{key}={value}")


def _collect_report(conn) -> dict[str, int]:
    """Собирает минимальные счетчики расхождений."""

    queries = {
        "legacy_count": "SELECT count(*) AS value FROM public.helpdesk_tickets",
        "normalized_count": "SELECT count(*) AS value FROM helpdesk.tickets",
        "pending_legacy": (
            "SELECT count(*) AS value FROM public.helpdesk_tickets "
            "WHERE ticket_id = 'PENDING'"
        ),
        "pending_normalized": (
            "SELECT count(*) AS value FROM helpdesk.tickets "
            "WHERE ticket_key = 'PENDING'"
        ),
        "only_public": """
            SELECT count(*) AS value
            FROM public.helpdesk_tickets p
            LEFT JOIN helpdesk.tickets t ON t.ticket_key = p.ticket_id
            WHERE t.id IS NULL
        """,
        "only_helpdesk": """
            SELECT count(*) AS value
            FROM helpdesk.tickets t
            LEFT JOIN public.helpdesk_tickets p ON p.ticket_id = t.ticket_key
            WHERE p.id IS NULL
        """,
        "duplicate_legacy_ticket_id": """
            SELECT count(*) AS value
            FROM (
                SELECT ticket_id
                FROM public.helpdesk_tickets
                GROUP BY ticket_id
                HAVING count(*) > 1
            ) d
        """,
        "duplicate_normalized_ticket_key": """
            SELECT count(*) AS value
            FROM (
                SELECT ticket_key
                FROM helpdesk.tickets
                GROUP BY ticket_key
                HAVING count(*) > 1
            ) d
        """,
        "mismatched_statuses": """
            SELECT count(*) AS value
            FROM public.helpdesk_tickets p
            JOIN helpdesk.tickets t ON t.ticket_key = p.ticket_id
            WHERE t.status_code != CASE p.status
                WHEN 'новое' THEN 'new'
                WHEN 'в работе' THEN 'in_progress'
                WHEN 'ожидает пользователя' THEN 'waiting_user'
                WHEN 'закрыто' THEN 'closed'
                ELSE 'new'
            END
        """,
        "mismatched_assignees": """
            SELECT count(*) AS value
            FROM public.helpdesk_tickets p
            JOIN helpdesk.tickets t ON t.ticket_key = p.ticket_id
            WHERE p.assignee_user_id IS DISTINCT FROM t.assignee_user_id
               OR p.assignee_name IS DISTINCT FROM t.assignee_name
        """,
        "mismatched_categories": """
            SELECT count(*) AS value
            FROM public.helpdesk_tickets p
            JOIN helpdesk.tickets t ON t.ticket_key = p.ticket_id
            LEFT JOIN helpdesk.categories c ON c.code = t.category_code
            WHERE p.category IS DISTINCT FROM c.display_name
        """,
        "orphan_comments": """
            SELECT count(*) AS value
            FROM helpdesk.ticket_comments c
            LEFT JOIN helpdesk.tickets t ON t.id = c.ticket_id
            WHERE t.id IS NULL
        """,
        "orphan_attachments": """
            SELECT count(*) AS value
            FROM helpdesk.ticket_attachments a
            LEFT JOIN helpdesk.tickets t ON t.id = a.ticket_id
            WHERE t.id IS NULL
        """,
        "orphan_events": """
            SELECT count(*) AS value
            FROM helpdesk.ticket_events e
            LEFT JOIN helpdesk.tickets t ON t.id = e.ticket_id
            WHERE t.id IS NULL
        """,
        "orphan_message_links": """
            SELECT count(*) AS value
            FROM integration.message_links ml
            LEFT JOIN helpdesk.tickets t ON t.id = ml.ticket_id
            WHERE t.id IS NULL
        """,
    }

    report: dict[str, int] = {}
    with conn.cursor() as cur:
        for key, sql in queries.items():
            cur.execute(sql)
            row = cur.fetchone()
            report[key] = int(row["value"]) if row else 0
    return report


if __name__ == "__main__":
    main()
