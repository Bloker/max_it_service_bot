from pathlib import Path
import argparse
import os
import sys

import psycopg

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.config import get_config


def main() -> None:
    args = _parse_args()
    if args.db:
        os.environ["MAX_TICKET_PG_DB"] = args.db

    cfg = get_config()
    if cfg.tickets.backend != "postgres":
        raise RuntimeError("Set MAX_TICKET_BACKEND=postgres before applying PostgreSQL migrations")

    migration_path = Path(args.migration_path)
    if not migration_path.is_absolute():
        migration_path = ROOT_DIR / migration_path
    if not migration_path.exists():
        migration_path = ROOT_DIR / "db" / "migrations" / args.migration_path
    sql = migration_path.read_text(encoding="utf-8")
    conninfo = (
        f"host={cfg.tickets.postgres_host} "
        f"port={cfg.tickets.postgres_port} "
        f"dbname={cfg.tickets.postgres_db} "
        f"user={cfg.tickets.postgres_user} "
        f"password={cfg.tickets.postgres_password} "
        f"sslmode={cfg.tickets.postgres_sslmode} "
        f"connect_timeout={cfg.tickets.postgres_connect_timeout_sec}"
    )

    with psycopg.connect(conninfo, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()

    print(f"Migration applied: {migration_path.name}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply a PostgreSQL SQL migration")
    parser.add_argument(
        "migration_path",
        nargs="?",
        default="db/migrations/20260407_normalized_schema.sql",
        help="Migration path relative to repository root, or migration filename",
    )
    parser.add_argument("--db", help="Override MAX_TICKET_PG_DB")
    return parser.parse_args()


if __name__ == "__main__":
    main()
