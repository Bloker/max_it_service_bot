"""Справочные данные Джамайки для test-only seed и будущего flow."""

from dataclasses import dataclass


JAMAICA_HOTEL_CODE = "jamaica"
JAMAICA_HOTEL_NAME = "Отель Джамайка"


@dataclass(frozen=True, slots=True)
class JamaicaLocationSeed:
    """Описание номера или домика Джамайки."""

    location_code: str
    location_type: str
    building_name: str
    room_number: str
    display_name: str
    sort_order: int


@dataclass(frozen=True, slots=True)
class JamaicaIssueCategorySeed:
    """Описание категории заявки по номеру."""

    code: str
    title: str
    sort_order: int


JAMAICA_ISSUE_CATEGORIES: tuple[JamaicaIssueCategorySeed, ...] = (
    JamaicaIssueCategorySeed(code="tv", title="ТВ", sort_order=10),
    JamaicaIssueCategorySeed(code="telephony", title="Телефония", sort_order=20),
    JamaicaIssueCategorySeed(code="internet", title="Интернет", sort_order=30),
    JamaicaIssueCategorySeed(code="lock", title="Замок", sort_order=40),
    JamaicaIssueCategorySeed(code="other", title="Прочее", sort_order=50),
)


def build_jamaica_locations() -> tuple[JamaicaLocationSeed, ...]:
    """Возвращает полный каталог из 253 объектов обслуживания Джамайки."""

    locations: list[JamaicaLocationSeed] = []
    sort_order = 10
    for building_name, ranges in (
        ("1 корпус", ((101, 123), (201, 226), (301, 326), (401, 425))),
        ("2 корпус", ((2101, 2120), (2201, 2220), (2301, 2321))),
        ("3 корпус", ((3101, 3120), (3201, 3221), (3301, 3321))),
    ):
        for start, end in ranges:
            for number in range(start, end + 1):
                room_number = str(number)
                locations.append(
                    JamaicaLocationSeed(
                        location_code=f"jamaica:{room_number}",
                        location_type="room",
                        building_name=building_name,
                        room_number=room_number,
                        display_name=f"Джамайка · {building_name} · номер {room_number}",
                        sort_order=sort_order,
                    )
                )
                sort_order += 10

    for number in range(1, 31):
        room_number = str(number)
        locations.append(
            JamaicaLocationSeed(
                location_code=f"jamaica:cottage:{room_number}",
                location_type="cottage",
                building_name="Домики",
                room_number=room_number,
                display_name=f"Джамайка · Домик {room_number}",
                sort_order=sort_order,
            )
        )
        sort_order += 10
    return tuple(locations)


def normalize_room_number(value: str) -> str:
    """Нормализует номер как строку без потери будущих буквенных суффиксов."""

    return " ".join(str(value or "").strip().split())
