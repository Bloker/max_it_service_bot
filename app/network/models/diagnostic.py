from dataclasses import dataclass


@dataclass(slots=True)
class DiagnosticResult:
    ok: bool
    title: str
    details: str

