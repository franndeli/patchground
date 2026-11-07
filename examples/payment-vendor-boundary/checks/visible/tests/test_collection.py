from datetime import UTC, datetime

import pytest

from billing.app import build_invoice_service
from billing.dunning import next_action
from billing.invoices import Invoice
from paysafe import PaysafeClient


def service(rc="00", amt=None, ccy="EUR", timeout=False):
    def transport(request):
        if timeout:
            raise TimeoutError("read timed out")
        return {"txn_ref": "ps-77", "amt_minor": amt or request["amt_minor"], "ccy": ccy, "rc": rc, "ts_ms": 1767225600250}

    return build_invoice_service(PaysafeClient(transport))


def invoice():
    return Invoice("inv-1", 4999, "EUR")


def test_approved_charge_marks_the_invoice_paid():
    paid = service("00").collect(invoice())
    assert (paid.status, paid.payment_ref, paid.failure) == ("paid", "ps-77", None)
    assert paid.paid_at == datetime(2026, 1, 1, 0, 0, 0, 250000, tzinfo=UTC)
    assert next_action(paid) == "none"


@pytest.mark.parametrize(
    ("rc", "status", "failure", "action"),
    [
        ("05", "declined", "card declined", "email: update card"),
        ("51", "declined", "insufficient funds", "email: top up and retry in 3 days"),
        ("91", "retry", "issuer unavailable", "retry in 1 hour"),
    ],
)
def test_unpaid_outcomes_and_dunning(rc, status, failure, action):
    result = service(rc).collect(invoice())
    assert (result.status, result.failure, result.paid_at) == (status, failure, None)
    assert next_action(result) == action


def test_timeout_is_retried():
    result = service(timeout=True).collect(invoice())
    assert (result.status, result.failure) == ("retry", "gateway timeout")
    assert next_action(result) == "retry in 1 hour"


def test_surprises_are_errors_not_outcomes():
    with pytest.raises(RuntimeError):
        service("12").collect(invoice())
    with pytest.raises(RuntimeError):
        service("00", amt=5000).collect(invoice())
    with pytest.raises(RuntimeError):
        service("00", ccy="USD").collect(invoice())


def test_paid_invoices_are_not_charged_twice():
    paid = service("00").collect(invoice())
    with pytest.raises(ValueError):
        service("00").collect(paid)
