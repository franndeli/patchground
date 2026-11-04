"""Single-worker notification queue with an injected sender."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal

Status = Literal["pending", "complete", "failed", "exhausted"]


@dataclass(frozen=True)
class Delivery:
    delivery_id: str
    payload: str
    due_at: int | None
    attempts: int = 0
    status: Status = "pending"


@dataclass(frozen=True)
class Response:
    status_code: int
    retry_after_ms: object = None


class DeliveryQueue:
    def __init__(self, sender: Callable[[Delivery], Response]) -> None:
        self._sender = sender
        self._deliveries: dict[str, Delivery] = {}

    def enqueue(self, delivery_id: str, payload: str, due_at: int) -> None:
        if delivery_id not in self._deliveries:
            self._deliveries[delivery_id] = Delivery(delivery_id, payload, due_at)

    def get(self, delivery_id: str) -> Delivery:
        return self._deliveries[delivery_id]

    def drain(self, now: int) -> tuple[str, ...]:
        ready = sorted(
            (
                delivery
                for delivery in self._deliveries.values()
                if delivery.status == "pending"
                and delivery.due_at is not None
                and delivery.due_at <= now
            ),
            key=lambda delivery: (delivery.due_at, delivery.delivery_id),
        )
        attempted: list[str] = []
        for delivery in ready:
            attempt = replace(delivery, attempts=delivery.attempts + 1)
            self._deliveries[delivery.delivery_id] = attempt
            attempted.append(delivery.delivery_id)
            try:
                response = self._sender(attempt)
            except TimeoutError:
                self._deliveries[delivery.delivery_id] = replace(
                    attempt, status="failed", due_at=None
                )
                continue
            status: Status = "complete" if 200 <= response.status_code < 300 else "failed"
            self._deliveries[delivery.delivery_id] = replace(attempt, status=status, due_at=None)
        return tuple(attempted)
