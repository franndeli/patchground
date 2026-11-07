"""Architecture checks: Paysafe is translated at one boundary and never reaches the domain."""

import ast
import dataclasses
from datetime import UTC, datetime
from pathlib import Path

import pytest

BILLING = Path(__file__).resolve().parents[1] / "src" / "billing"


def imports_paysafe(path: Path) -> bool:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names = [node.module]
        if any(name == "paysafe" or name.startswith("paysafe.") for name in names):
            return True
    return False


def test_only_the_gateway_adapter_and_the_composition_root_import_the_sdk():
    importers = {path.name for path in BILLING.rglob("*.py") if imports_paysafe(path)}
    assert importers <= {"paysafe_gateway.py", "app.py"}
    assert "paysafe_gateway.py" in importers


def test_invoice_holds_no_vendor_data():
    from billing.invoices import Invoice

    names = {field.name for field in dataclasses.fields(Invoice)}
    assert names == {"invoice_id", "amount_cents", "currency", "status", "paid_at", "payment_ref", "failure"}


class FakeGateway:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def charge(self, invoice_id, amount_cents, currency):
        self.calls.append((invoice_id, amount_cents, currency))
        if self.error:
            raise self.error
        return self.result


def test_domain_collects_through_the_port_with_a_fake():
    from billing.invoices import Invoice, InvoiceService
    from billing.payments import Outcome, PaymentGateway, PaymentResult, Reason

    when = datetime(2026, 2, 3, 4, 5, 6, tzinfo=UTC)
    gateway = FakeGateway(PaymentResult(Outcome.APPROVED, None, "ref-1", when))
    assert isinstance(gateway, PaymentGateway)
    paid = InvoiceService(gateway).collect(Invoice("inv-9", 1200, "GBP"))
    assert gateway.calls == [("inv-9", 1200, "GBP")]
    assert (paid.status, paid.paid_at, paid.payment_ref, paid.failure) == ("paid", when, "ref-1", None)

    declined = InvoiceService(FakeGateway(PaymentResult(Outcome.DECLINED, Reason.INSUFFICIENT_FUNDS, None, None)))
    result = declined.collect(Invoice("inv-10", 1200, "GBP"))
    assert (result.status, result.failure) == ("declined", "insufficient funds")

    retry = InvoiceService(FakeGateway(PaymentResult(Outcome.RETRY, Reason.GATEWAY_TIMEOUT, None, None)))
    assert retry.collect(Invoice("inv-11", 1200, "GBP")).status == "retry"


def test_gateway_errors_leave_the_invoice_untouched():
    from billing.invoices import Invoice, InvoiceService
    from billing.payments import PaymentGatewayError

    assert issubclass(PaymentGatewayError, RuntimeError)
    open_invoice = Invoice("inv-12", 300, "EUR")
    with pytest.raises(PaymentGatewayError):
        InvoiceService(FakeGateway(error=PaymentGatewayError("boom"))).collect(open_invoice)
    assert open_invoice == Invoice("inv-12", 300, "EUR")


def test_dunning_reads_domain_reasons():
    from billing.dunning import next_action
    from billing.invoices import Invoice
    from billing.payments import Reason

    assert next_action(Invoice("a", 1, "EUR", status="declined", failure=Reason.INSUFFICIENT_FUNDS)) == (
        "email: top up and retry in 3 days"
    )
    assert next_action(Invoice("b", 1, "EUR", status="declined", failure=Reason.CARD_DECLINED)) == "email: update card"


def adapter(rc="00", amt=None, ccy="EUR", timeout=False, ts_ms=1767225600250):
    from billing.paysafe_gateway import PaysafeGateway
    from paysafe import PaysafeClient

    def transport(request):
        if timeout:
            raise TimeoutError("slow")
        return {"txn_ref": "ps-1", "amt_minor": amt or request["amt_minor"], "ccy": ccy, "rc": rc, "ts_ms": ts_ms}

    return PaysafeGateway(PaysafeClient(transport))


def test_adapter_translates_every_known_code():
    from billing.payments import Outcome, PaymentGateway, PaymentResult, Reason

    assert isinstance(adapter(), PaymentGateway)
    assert adapter("00", ts_ms=1767225600999).charge("i", 10, "EUR") == PaymentResult(
        Outcome.APPROVED, None, "ps-1", datetime(2026, 1, 1, 0, 0, 0, 999000, tzinfo=UTC)
    )
    expected = {
        "05": (Outcome.DECLINED, Reason.CARD_DECLINED),
        "51": (Outcome.DECLINED, Reason.INSUFFICIENT_FUNDS),
        "91": (Outcome.RETRY, Reason.ISSUER_UNAVAILABLE),
    }
    for rc, (outcome, reason) in expected.items():
        assert adapter(rc).charge("i", 10, "EUR") == PaymentResult(outcome, reason, None, None), rc
    assert adapter(timeout=True).charge("i", 10, "EUR") == PaymentResult(Outcome.RETRY, Reason.GATEWAY_TIMEOUT, None, None)


def test_adapter_turns_vendor_surprises_into_domain_errors():
    from billing.payments import PaymentGatewayError

    for gateway in (adapter("12"), adapter("00", amt=11), adapter("00", ccy="USD")):
        with pytest.raises(PaymentGatewayError):
            gateway.charge("i", 10, "EUR")


def test_reasons_keep_their_wording():
    from billing.payments import Reason

    assert {reason.value for reason in Reason} == {
        "card declined", "insufficient funds", "issuer unavailable", "gateway timeout",
    }
