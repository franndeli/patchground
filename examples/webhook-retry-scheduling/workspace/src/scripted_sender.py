"""Deterministic fake sender: no network or system clock."""

from collections import deque
from collections.abc import Mapping, Sequence

from webhook_queue import Delivery, Response


class ScriptedSender:
    def __init__(self, scripts: Mapping[str, Sequence[Response | TimeoutError]]) -> None:
        self._scripts = {key: deque(outcomes) for key, outcomes in scripts.items()}
        self.calls: list[Delivery] = []

    def __call__(self, delivery: Delivery) -> Response:
        self.calls.append(delivery)
        if not self._scripts.get(delivery.delivery_id):
            raise RuntimeError("provide one scripted outcome for each expected send")
        outcome = self._scripts[delivery.delivery_id].popleft()
        if isinstance(outcome, TimeoutError):
            raise outcome
        return outcome
