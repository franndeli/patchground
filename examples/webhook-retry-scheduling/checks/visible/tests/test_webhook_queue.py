import pytest
from scripted_sender import ScriptedSender
from webhook_queue import DeliveryQueue, Response


def test_due_items_and_terminal_success():
    sender = ScriptedSender({"welcome": [Response(204)]})
    queue = DeliveryQueue(sender)
    queue.enqueue("welcome", '{"kind":"welcome"}', due_at=25)
    original = queue.get("welcome")
    assert (original.status, original.attempts, original.due_at) == ("pending", 0, 25)
    assert queue.drain(24) == ()
    assert queue.get("welcome") == original
    assert queue.drain(25) == ("welcome",)
    result = queue.get("welcome")
    assert (result.status, result.attempts, result.due_at) == ("complete", 1, None)
    assert queue.drain(999999) == ()
    assert original.attempts == 0
    assert sender.calls[0].attempts == 1
    assert sender.calls[0].due_at == 25
    assert sender.calls[0].status == "pending"


@pytest.mark.parametrize("outcome", [TimeoutError("slow"), Response(429), Response(503)])
def test_transient_failures_retry_at_the_exact_boundary(outcome):
    sender = ScriptedSender({"export": [outcome, Response(200)]})
    queue = DeliveryQueue(sender)
    queue.enqueue("export", "body", due_at=0)
    assert queue.drain(10) == ("export",)
    assert (queue.get("export").status, queue.get("export").due_at) == ("pending", 1010)
    assert queue.drain(1009) == ()
    assert queue.drain(1010) == ("export",)
    assert queue.get("export").status == "complete"
    assert queue.get("export").attempts == 2


def test_retry_after_and_three_total_attempts():
    sender = ScriptedSender(
        {
            "slow": [
                Response(429, 5000),
                TimeoutError("slow"),
                Response(503),
            ]
        }
    )
    queue = DeliveryQueue(sender)
    queue.enqueue("slow", "body", due_at=0)
    queue.drain(100)
    assert queue.get("slow").due_at == 5100
    queue.drain(5100)
    assert queue.get("slow").due_at == 7100
    queue.drain(7100)
    assert (queue.get("slow").status, queue.get("slow").attempts) == ("exhausted", 3)
    assert queue.get("slow").due_at is None
    assert queue.drain(100000) == ()


@pytest.mark.parametrize("retry_after", [None, -1, True, 1000.0, "5000", 0, 10])
def test_invalid_or_short_retry_after_uses_normal_delay(retry_after):
    sender = ScriptedSender({"limited": [Response(429, retry_after)]})
    queue = DeliveryQueue(sender)
    queue.enqueue("limited", "body", due_at=0)
    queue.drain(500)
    assert queue.get("limited").status == "pending"
    assert queue.get("limited").due_at == 1500


def test_failure_does_not_block_due_items_and_order_is_stable():
    sender = ScriptedSender(
        {
            "b": [Response(503)],
            "a": [TimeoutError("slow")],
            "early": [Response(302)],
            "future": [Response(200)],
        }
    )
    queue = DeliveryQueue(sender)
    for delivery_id, due_at in [("b", 10), ("future", 11), ("a", 10), ("early", 0)]:
        queue.enqueue(delivery_id, "body", due_at)
    assert queue.drain(10) == ("early", "a", "b")
    assert [call.delivery_id for call in sender.calls] == ["early", "a", "b"]
    assert queue.get("early").status == "failed"
    assert queue.get("a").due_at == 1010
    assert queue.get("b").due_at == 1010
    assert queue.get("future").attempts == 0


def test_duplicate_id_does_not_reset_pending_or_complete_delivery():
    sender = ScriptedSender({"one": [Response(503), Response(201)]})
    queue = DeliveryQueue(sender)
    queue.enqueue("one", "original", due_at=0)
    queue.drain(0)
    waiting = queue.get("one")
    queue.enqueue("one", "replacement", due_at=0)
    assert queue.get("one") == waiting
    queue.drain(1000)
    complete = queue.get("one")
    queue.enqueue("one", "another", due_at=0)
    assert queue.get("one") == complete
    assert complete.payload == "original"
    assert queue.drain(100000) == ()
