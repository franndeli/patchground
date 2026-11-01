"""Composition root used by the CLI and the tests."""

from __future__ import annotations

from orders.service import OrderService


def build_service(db_path: str, outbox: str) -> OrderService:
    return OrderService(db_path, outbox)
