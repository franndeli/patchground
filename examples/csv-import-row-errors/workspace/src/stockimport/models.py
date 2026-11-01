from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    sku: str
    quantity: int
    unit_price_cents: int


@dataclass(frozen=True)
class RowError:
    line: int
    column: str | None
    code: str
    message: str


@dataclass(frozen=True)
class ImportResult:
    items: list[Item]
    errors: list[RowError]


class ImportFailed(ValueError):
    """Raised when an import stops; ``error`` says why."""

    def __init__(self, error: RowError) -> None:
        super().__init__(f"line {error.line}: {error.message}")
        self.error = error
