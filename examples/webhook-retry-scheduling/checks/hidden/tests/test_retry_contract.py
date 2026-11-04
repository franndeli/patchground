import pytest
from webhook_queue import DeliveryQueue, Response


def test_empty_queue_and_due_time_order_across_failures():
    calls = []
    outcomes = {"aa": Response(500), "Z": TimeoutError(), "later": Response(204)}

    def send(delivery):
        calls.append((delivery.delivery_id, delivery.attempts, delivery.payload))
        outcome = outcomes[delivery.delivery_id]
        if isinstance(outcome, TimeoutError):
            raise outcome
        return outcome

    queue = DeliveryQueue(send)
    assert queue.drain(100) == ()
    queue.enqueue("later", "last", 4)
    queue.enqueue("aa", "second", 3)
    queue.enqueue("Z", "first", 3)
    queue.enqueue("sleeping", "future", 101)
    sleeping = queue.get("sleeping")
    assert queue.drain(100) == ("Z", "aa", "later")
    assert calls == [("Z", 1, "first"), ("aa", 1, "second"), ("later", 1, "last")]
    assert queue.get("sleeping") == sleeping
    assert queue.get("Z").due_at == 1100
    assert queue.get("aa").due_at == 1100
    assert queue.get("later").status == "complete"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (199, "failed"),
        (200, "complete"),
        (206, "complete"),
        (299, "complete"),
        (300, "failed"),
        (307, "failed"),
        (400, "failed"),
        (408, "failed"),
        (422, "failed"),
        (429, "pending"),
        (499, "failed"),
        (500, "pending"),
        (599, "pending"),
        (600, "failed"),
    ],
)
def test_response_classification_and_terminal_due_times(status, expected):
    calls = []

    def send(delivery):
        calls.append(delivery)
        return Response(status, 9999)

    queue = DeliveryQueue(send)
    queue.enqueue("id", "payload", 10)
    assert queue.drain(10) == ("id",)
    result = queue.get("id")
    assert result.status == expected
    assert result.attempts == 1
    if expected == "pending":
        assert result.due_at == (10009 if status == 429 else 1010)
    else:
        assert result.due_at is None
    if expected != "pending":
        assert queue.drain(1000000) == ()
        assert len(calls) == 1


@pytest.mark.parametrize("retry_after", [None, -100, False, True, 9000.0, "9000", [], {}])
def test_retry_after_rejects_non_integer_or_negative_durations(retry_after):
    queue = DeliveryQueue(lambda _: Response(429, retry_after))
    queue.enqueue("id", "payload", 0)
    queue.drain(200)
    assert queue.get("id").due_at == 1200
    assert queue.get("id").status == "pending"


@pytest.mark.parametrize("retry_after", [0, 999, 1000, 1001, 9000])
def test_valid_retry_after_uses_maximum_delay_on_each_attempt(retry_after):
    queue = DeliveryQueue(lambda _: Response(429, retry_after))
    queue.enqueue("id", "payload", 0)
    queue.drain(37)
    first_due = 37 + max(1000, retry_after)
    assert queue.get("id").due_at == first_due
    assert queue.drain(first_due - 1) == ()
    assert queue.drain(first_due) == ("id",)
    second_due = first_due + max(2000, retry_after)
    assert queue.get("id").due_at == second_due
    assert queue.drain(second_due - 1) == ()
    assert queue.drain(second_due) == ("id",)
    terminal = queue.get("id")
    assert (terminal.status, terminal.attempts, terminal.due_at) == ("exhausted", 3, None)
    queue.enqueue("id", "reset", 0)
    assert queue.get("id") == terminal
    assert queue.drain(second_due + 999999) == ()


@pytest.mark.parametrize("failure", ["timeout", 500, 599, 429])
def test_retryable_failures_get_exactly_three_attempts_and_no_tight_loop(failure):
    calls = []

    def send(delivery):
        calls.append(delivery)
        if failure == "timeout":
            raise TimeoutError("simulated")
        return Response(failure)

    queue = DeliveryQueue(send)
    queue.enqueue("id", "payload", 0)
    original = queue.get("id")
    assert queue.drain(10000) == ("id",)
    assert queue.get("id").due_at == 11000
    assert queue.drain(10000) == ()
    assert queue.drain(11000) == ("id",)
    assert queue.get("id").due_at == 13000
    assert queue.drain(12999) == ()
    assert queue.drain(13000) == ("id",)
    terminal = queue.get("id")
    assert (terminal.status, terminal.attempts, terminal.due_at) == ("exhausted", 3, None)
    assert queue.drain(999999) == ()
    assert [call.attempts for call in calls] == [1, 2, 3]
    assert [call.due_at for call in calls] == [0, 11000, 13000]
    assert all(call.status == "pending" for call in calls)
    assert (original.attempts, original.status, original.due_at) == (0, "pending", 0)


@pytest.mark.parametrize(("last_status", "terminal_status"), [(299, "complete"), (401, "failed")])
def test_third_attempt_can_succeed_or_fail_permanently(last_status, terminal_status):
    responses = iter([Response(503), Response(429), Response(last_status)])
    queue = DeliveryQueue(lambda _: next(responses))
    queue.enqueue("id", "payload", 0)
    queue.drain(0)
    queue.drain(1000)
    queue.drain(3000)
    final = queue.get("id")
    assert (final.status, final.attempts, final.due_at) == (terminal_status, 3, None)
    queue.enqueue("id", "reset", 0)
    assert queue.get("id") == final
    assert queue.drain(99999) == ()


def test_duplicate_identity_before_send_and_after_a_permanent_failure():
    calls = []

    def send(delivery):
        calls.append(delivery)
        return Response(403)

    queue = DeliveryQueue(send)
    queue.enqueue("id", "original", 50)
    snapshot = queue.get("id")
    queue.enqueue("id", "replacement", 0)
    assert queue.get("id") == snapshot
    assert queue.drain(49) == ()
    assert queue.drain(50) == ("id",)
    failed = queue.get("id")
    queue.enqueue("id", "replacement", 0)
    assert queue.get("id") == failed
    assert failed.payload == "original"
    assert queue.drain(10000) == ()
    assert len(calls) == 1


def test_second_delay_is_measured_from_late_drain_and_ignores_server_retry_after():
    responses = iter([Response(500, 50000), Response(503, 90000), Response(204)])
    queue = DeliveryQueue(lambda _: next(responses))
    queue.enqueue("id", "body", -100)
    queue.drain(400)
    assert queue.get("id").due_at == 1400
    queue.drain(8000)
    assert queue.get("id").due_at == 10000
    assert queue.drain(9999) == ()
    queue.drain(10000)
    assert queue.get("id").status == "complete"


def test_new_delivery_proceeds_while_an_older_one_waits():
    calls = []
    responses = {"old": iter([Response(503), Response(200)]), "new": iter([Response(200)])}

    def send(delivery):
        calls.append(delivery.delivery_id)
        return next(responses[delivery.delivery_id])

    queue = DeliveryQueue(send)
    queue.enqueue("old", "body", 0)
    queue.drain(0)
    queue.enqueue("new", "body", 5)
    assert queue.drain(5) == ("new",)
    assert calls == ["old", "new"]
    assert queue.get("old").attempts == 1
    assert queue.drain(1000) == ("old",)
    assert calls == ["old", "new", "old"]
