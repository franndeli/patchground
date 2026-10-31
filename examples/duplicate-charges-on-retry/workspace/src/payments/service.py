from payments.gateway import OfflineGateway
from payments.models import GatewayTimeout, Receipt


class PaymentService:
    def __init__(self, gateway: OfflineGateway, max_attempts: int = 3) -> None:
        if type(max_attempts) is not int or max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer")
        self.gateway = gateway
        self.max_attempts = max_attempts

    def pay(self, request_id: str, amount_cents: int) -> Receipt:
        """Return a receipt, retrying only ambiguous transport failures."""
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must be nonempty")
        for attempt in range(self.max_attempts):
            provider_key = f"{request_id}:attempt-{attempt}"
            try:
                return self.gateway.charge(provider_key, amount_cents)
            except GatewayTimeout:
                if attempt + 1 == self.max_attempts:
                    raise
        raise AssertionError("unreachable")
