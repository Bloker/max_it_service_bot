"""Seed простых записей Jamaica Knowledge Base в test_dev_max."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from psycopg.rows import dict_row

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.infrastructure.database.psycopg_connection import connect_postgres  # noqa: E402
from config.config import get_config  # noqa: E402

SEED_ITEMS = (
    ("tv", "Нет сигнала", "Проверить питание ТВ, HDMI-вход и перезапуск приставки.", 10),
    ("tv", "Не работает пульт", "Проверить батарейки пульта и видимость ИК-приемника телевизора.", 20),
    ("tv", "Не включается телевизор", "Проверить питание, розетку и кнопку включения на корпусе ТВ.", 30),
    ("telephony", "Нет гудка", "Проверить патч-корд телефона и линию на кроссе.", 40),
    ("telephony", "Не работает телефон в номере", "Проверить аппарат, кабель и порт на голосовом шлюзе.", 50),
    ("internet", "Гость не видит Wi-Fi", "Проверить уровень сигнала и доступность SSID в номере.", 60),
    ("internet", "Не открывается страница авторизации", "Подключиться к Wi-Fi и открыть captive portal вручную.", 70),
    ("internet", "Проверить ваучер гостя", "Проверить наличие ваучера и срок его действия.", 80),
    ("lock", "Карта не открывает номер", "Проверить карту гостя и перевыпустить ключ при необходимости.", 90),
    ("lock", "Замок не реагирует", "Проверить индикацию замка и питание устройства.", 100),
    ("lock", "Проверить батарейку замка", "Осмотреть батарейный отсек и заменить батарейки при разряде.", 110),
    ("other", "Нестандартная заявка", "Уточнить симптом, номер и время проявления проблемы.", 120),
)

SCOPE_SEED_ITEMS = (
    ("jamaica", "Джамайка", "hotel", 10),
    ("general_it", "Общее IT", "global", 20),
    ("infrastructure", "Сеть и инфраструктура", "infrastructure", 30),
    ("systems", "Системы", "system", 40),
)


def main() -> None:
    args = _parse_args()
    if args.db:
        os.environ["MAX_TICKET_PG_DB"] = args.db
    cfg = get_config()
    if cfg.tickets.backend != "postgres":
        raise RuntimeError("Set MAX_TICKET_BACKEND=postgres before seed")
    database = cfg.tickets.postgres_db
    if database != "test_dev_max" and not args.allow_non_test:
        raise RuntimeError("Refusing to seed non-test database")

    conninfo = (
        f"host={cfg.tickets.postgres_host} "
        f"port={cfg.tickets.postgres_port} "
        f"dbname={database} "
        f"user={cfg.tickets.postgres_user} "
        f"password={cfg.tickets.postgres_password} "
        f"sslmode={cfg.tickets.postgres_sslmode} "
        f"connect_timeout={cfg.tickets.postgres_connect_timeout_sec}"
    )
    created = seed_jamaica_knowledge_base(conninfo)
    print(f"Jamaica KB seed complete: database={database} rows_upserted={created}")


def seed_jamaica_knowledge_base(conninfo: str) -> int:
    """Идемпотентно наполняет тестовую KB стартовыми статьями."""

    with connect_postgres(conninfo, row_factory=dict_row, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM auth.hotels WHERE code = %s", ("jamaica",))
            hotel_row = cur.fetchone()
            if hotel_row is None:
                raise RuntimeError("Hotel jamaica not found. Run seed_jamaica_test_data.py first.")
            hotel_id = int(hotel_row["id"])
            scope_ids = _seed_scopes(cur, hotel_id)
            jamaica_scope_id = scope_ids["jamaica"]

            created = 0
            for category_code, title, body, sort_order in SEED_ITEMS:
                cur.execute(
                    """
                    SELECT ic.id
                    FROM helpdesk.issue_categories ic
                    JOIN helpdesk.hotel_issue_categories hic
                      ON hic.category_id = ic.id
                    WHERE hic.hotel_id = %s
                      AND ic.code = %s
                    LIMIT 1
                    """,
                    (hotel_id, category_code),
                )
                category_row = cur.fetchone()
                if category_row is None:
                    continue
                category_id = int(category_row["id"])
                cur.execute(
                    """
                    SELECT id, body, sort_order
                    FROM helpdesk.knowledge_articles
                    WHERE scope_id = %s
                      AND hotel_id = %s
                      AND category_id = %s
                      AND title = %s
                      AND metadata ->> 'seed' = 'jamaica'
                    LIMIT 1
                    """,
                    (jamaica_scope_id, hotel_id, category_id, title),
                )
                existing_row = cur.fetchone()
                if existing_row is not None:
                    cur.execute(
                        """
                        UPDATE helpdesk.knowledge_articles
                        SET body = %s,
                            sort_order = %s,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (body, sort_order, int(existing_row["id"])),
                    )
                    continue
                cur.execute(
                    """
                    INSERT INTO helpdesk.knowledge_articles(
                        scope_id, hotel_id, category_id, title, body,
                        is_active, sort_order, metadata
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        TRUE, %s, '{"seed":"jamaica"}'::jsonb
                    )
                    """,
                    (jamaica_scope_id, hotel_id, category_id, title, body, sort_order),
                )
                created += cur.rowcount
            cur.execute(
                """
                UPDATE helpdesk.knowledge_articles
                SET scope_id = %s
                WHERE hotel_id = %s
                  AND scope_id IS NULL
                """,
                (jamaica_scope_id, hotel_id),
            )
        conn.commit()
    return created


def _seed_scopes(cur, hotel_id: int) -> dict[str, int]:
    """Создает базовые разделы KB и возвращает их ID по коду."""

    scope_ids: dict[str, int] = {}
    for code, title, scope_type, sort_order in SCOPE_SEED_ITEMS:
        current_hotel_id = hotel_id if code == "jamaica" else None
        cur.execute(
            """
            INSERT INTO helpdesk.knowledge_scopes(code, title, scope_type, hotel_id, sort_order)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (code) DO UPDATE
            SET title = EXCLUDED.title,
                scope_type = EXCLUDED.scope_type,
                hotel_id = EXCLUDED.hotel_id,
                sort_order = EXCLUDED.sort_order,
                updated_at = NOW()
            RETURNING id
            """,
            (code, title, scope_type, current_hotel_id, sort_order),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(f"Could not upsert knowledge scope {code}")
        scope_ids[code] = int(row["id"])
    return scope_ids


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Override MAX_TICKET_PG_DB")
    parser.add_argument("--allow-non-test", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
