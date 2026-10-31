from collections import deque

from payments.models import GatewayTimeout, PaymentDeclined, Receipt, RequestConflict


class OfflineGateway:
    """Deterministic provider simulator; state lasts for this instance only.

    Events: ok, timeout_before, timeout_after, declined. An already committed
    key returns its receipt before consuming any event. No network or credentials.
    """

    def __init__(self, events: tuple[str, ...] = ()) -> None:
        self._events = deque(events)
        self.charges: dict[str, Receipt] = {}
        self.calls: list[tuple[str, int]] = []

    def charge(self, key: str, amount_cents: int) -> Receipt:
        if not key or type(amount_cents) is not int or amount_cents <= 0:
            raise ValueError("key and positive integer amount_cents required")
        self.calls.append((key, amount_cents))
        if key in self.charges:
            receipt = self.charges[key]
            if receipt.amount_cents != amount_cents:
                raise RequestConflict("request already used for another amount")
            return receipt
        event = self._events.popleft() if self._events else "ok"
        if event == "timeout_before":
            raise GatewayTimeout("connection lost before acceptance")
        if event == "declined":
            raise PaymentDeclined("payment declined")
        if event not in {"ok", "timeout_after"}:
            raise ValueError("unknown simulator event")
        receipt = Receipt(f"charge-{len(self.charges) + 1:04d}", amount_cents)
        self.charges[key] = receipt
        if event == "timeout_after":
            raise GatewayTimeout("response lost after acceptance")
        return receipt
