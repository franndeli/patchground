"""SQLite persistence for confirmed orders."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from orders.models import Order, OrderLine

_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    customer_email TEXT NOT NULL,
    lines TEXT NOT NULL,
    status TEXT NOT NULL
)
"""


class SqliteOrderRepository:
    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        with sqlite3.connect(self._path) as connection:
            connection.execute(_SCHEMA)

    def save_confirmed(self, order: Order) -> None:
        lines = json.dumps([line.__dict__ for line in order.lines])
        with sqlite3.connect(self._path) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO orders VALUES (?, ?, ?, ?)",
                (order.order_id, order.customer_email, lines, "confirmed"),
            )

    def get(self, order_id: str) -> Order | None:
        with sqlite3.connect(self._path) as connection:
            row = connection.execute(
                "SELECT order_id, customer_email, lines FROM orders WHERE order_id = ?",
                (order_id,),
            ).fetchone()
        if row is None:
            return None
        lines = tuple(OrderLine(**item) for item in json.loads(row[2]))
        return Order(order_id=row[0], customer_email=row[1], lines=lines)
