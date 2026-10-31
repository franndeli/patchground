import pytest
from payments.gateway import OfflineGateway
from payments.models import GatewayTimeout, PaymentDeclined
from payments.service import PaymentService


def test_successful_checkout():
    gateway = OfflineGateway()
    receipt = PaymentService(gateway).pay("order-a", 1250)
    assert receipt.amount_cents == 1250
    assert len(gateway.charges) == 1


def test_lost_success_response_does_not_charge_twice():
    gateway = OfflineGateway(("timeout_after", "ok"))
    receipt = PaymentService(gateway).pay("order-b", 2500)
    assert receipt.amount_cents == 2500
    assert len(gateway.charges) == 1


def test_decline_is_terminal():
    gateway = OfflineGateway(("declined", "ok"))
    with pytest.raises(PaymentDeclined):
        PaymentService(gateway).pay("order-c", 500)
    assert len(gateway.calls) == 1
    assert not gateway.charges


def test_transport_retries_are_bounded():
    gateway = OfflineGateway(("timeout_before",) * 4)
    with pytest.raises(GatewayTimeout):
        PaymentService(gateway, max_attempts=2).pay("order-d", 500)
    assert len(gateway.calls) == 2
    assert not gateway.charges
