"""Confirm orders: persist them and tell the customer."""

from __future__ import annotations

from orders.models import Order
from orders.smtp_gateway import SmtpNotifier
from orders.sqlite_store import SqliteOrderRepository


def format_confirmation(order: Order) -> tuple[str, str]:
    """Subject and body of the confirmation message. Shared by every channel."""
    subject = f"Order {order.order_id} confirmed"
    lines = [f"- {line.quantity} x {line.sku} @ {line.unit_price_cents / 100:.2f}" for line in order.lines]
    body = "\n".join(["Thanks for your order.", *lines, f"Total: {order.total_cents / 100:.2f}"])
    return subject, body


class OrderService:
    def __init__(self, db_path: str, outbox: str) -> None:
        self._db_path = db_path
        self._outbox = outbox

    def confirm(self, order: Order) -> None:
        if not order.lines:
            raise ValueError("an order needs at least one line")
        SqliteOrderRepository(self._db_path).save_confirmed(order)
        subject, body = format_confirmation(order)
        SmtpNotifier(self._outbox).send(order.customer_email, subject, body)

    def find(self, order_id: str) -> Order | None:
        return SqliteOrderRepository(self._db_path).get(order_id)
