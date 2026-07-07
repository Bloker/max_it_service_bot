"""PostgreSQL repository hotel/location справочников HelpDesk."""

import threading

from psycopg.rows import dict_row

from app.helpdesk.repositories.location_repository import (
    HotelRef,
    IssueCategoryRef,
    LocationRef,
)
from app.infrastructure.database.psycopg_connection import connect_postgres


class PostgresLocationRepository:
    """Читает отели, номера и hotel-specific категории из PostgreSQL."""

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
        return connect_postgres(self._conninfo, row_factory=dict_row)

    def find_hotel_by_code(self, code: str) -> HotelRef | None:
        """Возвращает активный отель по коду."""

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, code, name
                    FROM auth.hotels
                    WHERE code = %s AND is_active = TRUE
                    """,
                    (code,),
                )
                row = cur.fetchone()
        return _hotel(row)

    def find_user_default_hotel(self, user_id: int) -> HotelRef | None:
        """Возвращает текущий активный отель пользователя MAX."""

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT h.id, h.code, h.name
                    FROM auth.users u
                    JOIN auth.user_hotel_memberships hm
                      ON hm.user_id = u.id AND hm.valid_to IS NULL
                    JOIN auth.hotels h ON h.id = hm.hotel_id
                    WHERE u.external_user_id = %s AND h.is_active = TRUE
                    ORDER BY hm.valid_from DESC
                    LIMIT 1
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
        return _hotel(row)

    def find_location_by_room_number(self, hotel_id: int, room_number: str) -> LocationRef | None:
        """Возвращает активный объект обслуживания по номеру в рамках отеля."""

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, hotel_id, location_code, location_type, building_name,
                           room_number, display_name
                    FROM helpdesk.locations
                    WHERE hotel_id = %s
                      AND room_number = %s
                      AND is_active = TRUE
                    LIMIT 1
                    """,
                    (hotel_id, room_number),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return LocationRef(
            id=int(row["id"]),
            hotel_id=int(row["hotel_id"]),
            location_code=str(row["location_code"]),
            location_type=str(row["location_type"]),
            building_name=str(row["building_name"]) if row["building_name"] is not None else None,
            room_number=str(row["room_number"]),
            display_name=str(row["display_name"]),
        )

    def list_issue_categories_for_hotel(
        self,
        hotel_id: int,
        *,
        requires_location: bool | None = None,
    ) -> tuple[IssueCategoryRef, ...]:
        """Возвращает активные категории, включенные для отеля."""

        params: list[object] = [hotel_id]
        filter_sql = ""
        if requires_location is not None:
            filter_sql = "AND c.requires_location = %s"
            params.append(requires_location)

        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT c.id, c.code, c.title, c.requires_location, hic.sort_order
                    FROM helpdesk.hotel_issue_categories hic
                    JOIN helpdesk.issue_categories c ON c.id = hic.category_id
                    WHERE hic.hotel_id = %s
                      AND hic.is_enabled = TRUE
                      AND c.is_active = TRUE
                      {filter_sql}
                    ORDER BY hic.sort_order, c.title
                    """,
                    tuple(params),
                )
                rows = cur.fetchall()
        return tuple(
            IssueCategoryRef(
                id=int(row["id"]),
                code=str(row["code"]),
                title=str(row["title"]),
                requires_location=bool(row["requires_location"]),
                sort_order=int(row["sort_order"]),
            )
            for row in rows
        )


def _hotel(row) -> HotelRef | None:
    if row is None:
        return None
    return HotelRef(id=int(row["id"]), code=str(row["code"]), name=str(row["name"]))
