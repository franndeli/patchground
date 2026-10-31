from dataclasses import dataclass


class GatewayTimeout(TimeoutError):
    """Transport outcome is unknown; retry is allowed."""


class PaymentDeclined(Exception):
    """Terminal rejection; do not retry."""


class RequestConflict(Exception):
    """A request identity was reused with different payment details."""


@dataclass(frozen=True)
class Receipt:
    charge_id: str
    amount_cents: int
