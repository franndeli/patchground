import pytest
from payments.gateway import OfflineGateway
from payments.models import GatewayTimeout, RequestConflict
from payments.service import PaymentService


def test_ambiguous_acceptance_has_one_ledger_entry():
    gateway = OfflineGateway(("timeout_before", "timeout_after", "ok"))
    receipt = PaymentService(gateway).pay("invoice-71", 8317)
    assert len(gateway.charges) == 1
    assert list(gateway.charges.values()) == [receipt]
    assert len(gateway.calls) == 3


def test_replay_from_another_service_returns_original_receipt():
    gateway = OfflineGateway(("timeout_after", "ok"))
    first = PaymentService(gateway).pay("invoice-72", 1800)
    second = PaymentService(gateway).pay("invoice-72", 1800)
    assert first == second
    assert len(gateway.charges) == 1


def test_equal_amounts_with_different_ids_are_distinct():
    gateway = OfflineGateway()
    service = PaymentService(gateway)
    first = service.pay("invoice-73", 999)
    second = service.pay("invoice-74", 999)
    assert first.charge_id != second.charge_id
    assert len(gateway.charges) == 2


def test_changed_amount_after_ambiguous_acceptance_is_rejected():
    gateway = OfflineGateway(("timeout_after", "ok"))
    service = PaymentService(gateway)
    service.pay("invoice-75", 4100)
    before = len(gateway.calls)
    with pytest.raises(RequestConflict):
        service.pay("invoice-75", 4200)
    assert len(gateway.calls) == before + 1
    assert len(gateway.charges) == 1


def test_later_invocation_recovers_accepted_charge_after_exhaustion():
    gateway = OfflineGateway(("timeout_after",))
    with pytest.raises(GatewayTimeout):
        PaymentService(gateway, max_attempts=1).pay("invoice-76", 300)
    receipt = PaymentService(gateway).pay("invoice-76", 300)
    assert list(gateway.charges.values()) == [receipt]
    assert len(gateway.calls) == 2


def test_before_acceptance_retry_recovers():
    gateway = OfflineGateway(("timeout_before", "ok"))
    receipt = PaymentService(gateway).pay("invoice-77", 700)
    assert list(gateway.charges.values()) == [receipt]
    assert len(gateway.calls) == 2


def test_final_timeout_is_exposed_without_extra_attempts():
    gateway = OfflineGateway(("timeout_before",) * 5)
    with pytest.raises(GatewayTimeout, match="before acceptance"):
        PaymentService(gateway, max_attempts=3).pay("invoice-78", 2200)
    assert len(gateway.calls) == 3
    assert not gateway.charges


@pytest.mark.parametrize("amount", [0, -1, True, 1.5, "100"])
def test_invalid_amount_does_not_create_charge(amount):
    gateway = OfflineGateway()
    with pytest.raises(ValueError):
        PaymentService(gateway).pay("invoice-79", amount)
    assert not gateway.charges
    assert not gateway.calls


@pytest.mark.parametrize("request_id", ["", "  ", None])
def test_invalid_request_identity_does_not_reach_provider(request_id):
    gateway = OfflineGateway()
    with pytest.raises(ValueError):
        PaymentService(gateway).pay(request_id, 100)
    assert not gateway.calls


@pytest.mark.parametrize("limit", [0, -2, True, 1.5])
def test_invalid_retry_limit_is_rejected(limit):
    with pytest.raises(ValueError):
        PaymentService(OfflineGateway(), max_attempts=limit)
