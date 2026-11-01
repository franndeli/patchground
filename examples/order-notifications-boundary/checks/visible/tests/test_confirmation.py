import json

from orders import Order, OrderLine
from orders.app import build_service


def order(order_id="o-1"):
    return Order(order_id, "ada@example.test", (OrderLine("chair", 2, 4999), OrderLine("lamp", 1, 1500)))


def test_confirm_persists_and_emails(tmp_path):
    outbox = tmp_path / "outbox.jsonl"
    service = build_service(str(tmp_path / "orders.db"), str(outbox))
    service.confirm(order())
    assert service.find("o-1") == order()
    sent = [json.loads(line) for line in outbox.read_text().splitlines()]
    assert sent == [
        {
            "to": "ada@example.test",
            "subject": "Order o-1 confirmed",
            "body": "Thanks for your order.\n- 2 x chair @ 49.99\n- 1 x lamp @ 15.00\nTotal: 114.98",
        }
    ]


def test_empty_order_is_rejected_before_any_side_effect(tmp_path):
    outbox = tmp_path / "outbox.jsonl"
    service = build_service(str(tmp_path / "orders.db"), str(outbox))
    try:
        service.confirm(Order("o-2", "ada@example.test", ()))
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
    assert service.find("o-2") is None
    assert not outbox.exists()


def test_unknown_order_is_none(tmp_path):
    service = build_service(str(tmp_path / "orders.db"), str(tmp_path / "outbox.jsonl"))
    assert service.find("missing") is None
