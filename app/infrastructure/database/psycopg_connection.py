"""Общие helper-функции для psycopg-подключений."""

from typing import Any


def connect_utf8(conninfo: str, **kwargs: Any):
    """Открывает psycopg-соединение и принудительно включает UTF-8 client encoding."""

    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "PostgreSQL backend requires psycopg. Install dependencies from requirements.txt"
        ) from exc

    conn = psycopg.connect(conninfo, **kwargs)
    conn.execute("SET client_encoding TO 'UTF8'")
    return conn
