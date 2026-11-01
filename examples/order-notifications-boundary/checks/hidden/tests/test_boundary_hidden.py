"""Architecture checks: the service depends on ports, not on SQLite or SMTP."""

import ast
import importlib
import inspect
from pathlib import Path

import pytest

from orders import Order, OrderLine

SRC = Path(__file__).resolve().parents[1] / "src" / "orders"
INFRASTRUCTURE = {"orders.sqlite_store", "orders.smtp_gateway", "sqlite3", "smtplib"}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_service_module_has_no_infrastructure_imports():
    assert not imported_modules(SRC / "service.py") & INFRASTRUCTURE


def test_ports_module_defines_runtime_checkable_protocols():
    ports = importlib.import_module("orders.ports")
    for name in ("OrderRepository", "Notifier"):
        port = getattr(ports, name)
        assert getattr(port, "_is_protocol", False), f"{name} must be a typing.Protocol"
        assert getattr(port, "_is_runtime_protocol", False), f"{name} must be @runtime_checkable"


def test_adapters_satisfy_their_ports(tmp_path):
    ports = importlib.import_module("orders.ports")
    from orders.smtp_gateway import SmtpNotifier
    from orders.sqlite_store import SqliteOrderRepository

    assert isinstance(SqliteOrderRepository(tmp_path / "db"), ports.OrderRepository)
    assert isinstance(SmtpNotifier(tmp_path / "out"), ports.Notifier)


class MemoryRepository:
    def __init__(self):
        self.saved = {}

    def save_confirmed(self, order):
        self.saved[order.order_id] = order

    def get(self, order_id):
        return self.saved.get(order_id)


class MemoryNotifier:
    def __init__(self):
        self.sent = []

    def send(self, to, subject, body):
        self.sent.append((to, subject, body))


def test_service_takes_injected_ports_by_keyword():
    from orders.service import OrderService

    parameters = inspect.signature(OrderService).parameters
    assert {"repository", "notifier"} <= set(parameters)
    repository, notifier = MemoryRepository(), MemoryNotifier()
    service = OrderService(repository=repository, notifier=notifier)
    order = Order("o-9", "grace@example.test", (OrderLine("desk", 1, 20000),))
    service.confirm(order)
    assert repository.saved == {"o-9": order}
    assert notifier.sent == [
        ("grace@example.test", "Order o-9 confirmed", "Thanks for your order.\n- 1 x desk @ 200.00\nTotal: 200.00")
    ]
    assert service.find("o-9") == order


def test_service_does_not_construct_adapters_itself():
    from orders.service import OrderService

    with pytest.raises(TypeError):
        OrderService("orders.db", "outbox.jsonl")
