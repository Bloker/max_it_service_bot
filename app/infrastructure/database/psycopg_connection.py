"""Общие helper-функции для psycopg-подключений."""

import re
from typing import Any

_CLIENT_ENCODING_RE = re.compile(r"^[A-Za-z0-9_]+$")


def connect_postgres(
    conninfo: str,
    *,
    client_encoding: str | None = None,
    **kwargs: Any,
):
    """Открывает обычное psycopg-соединение.

    Production-БД после rebuild работает в UTF8, поэтому кодировка клиента
    не переопределяется без явной необходимости.
    """
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "PostgreSQL backend requires psycopg. Install dependencies from requirements.txt"
        ) from exc

    conn = psycopg.connect(conninfo, **kwargs)
    if client_encoding:
        if not _CLIENT_ENCODING_RE.fullmatch(client_encoding):
            raise ValueError("client_encoding contains unsupported characters")
        conn.execute(f"SET client_encoding TO {client_encoding!r}")
    return conn


def connect_utf8(conninfo: str, **kwargs: Any):
    """Совместимый alias для старых импортов.

    Исторически helper принудительно включал UTF8 из-за SQL_ASCII-БД.
    После миграции production-БД в UTF8 это больше не требуется.
    """
    return connect_postgres(conninfo, **kwargs)
