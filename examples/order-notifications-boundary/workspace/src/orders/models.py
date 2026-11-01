from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OrderLine:
    sku: str
    quantity: int
    unit_price_cents: int

    @property
    def total_cents(self) -> int:
        return self.quantity * self.unit_price_cents


@dataclass(frozen=True)
class Order:
    order_id: str
    customer_email: str
    lines: tuple[OrderLine, ...] = field(default_factory=tuple)

    @property
    def total_cents(self) -> int:
        return sum(line.total_cents for line in self.lines)
