"""Модели результатов сетевой диагностики."""

from dataclasses import dataclass


@dataclass(slots=True)
class DiagnosticResult:
    """Результат выполнения сетевого диагностического инструмента."""

    ok: bool
    title: str
    details: str
