"""Collect payment for an invoice through Paysafe."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from paysafe import PaysafeClient, PsResponse, PsTimeout

DECLINES = {"05": "card declined", "51": "insufficient funds"}


@dataclass
class Invoice:
    invoice_id: str
    amount_cents: int
    currency: str
    status: str = "open"  # open | paid | declined | retry
    paid_at: datetime | None = None
    payment_ref: str | None = None
    failure: str | None = None
    last_response: PsResponse | None = None


class InvoiceService:
    def __init__(self, client: PaysafeClient) -> None:
        self._client = client

    def collect(self, invoice: Invoice) -> Invoice:
        if invoice.status == "paid":
            raise ValueError(f"invoice {invoice.invoice_id} is already paid")
        try:
            response = self._client.charge(invoice.invoice_id, invoice.amount_cents, invoice.currency)
        except PsTimeout:
            invoice.status, invoice.failure = "retry", "gateway timeout"
            return invoice
        if (response.amt_minor, response.ccy) != (invoice.amount_cents, invoice.currency):
            raise RuntimeError(f"paysafe charged {response.amt_minor} {response.ccy} for {invoice.invoice_id}")
        if response.rc == "00":
            invoice.status, invoice.failure = "paid", None
            invoice.paid_at = datetime.fromtimestamp(response.ts_ms / 1000, UTC)
            invoice.payment_ref = response.txn_ref
        elif response.rc in DECLINES:
            invoice.status, invoice.failure = "declined", DECLINES[response.rc]
        elif response.rc == "91":
            invoice.status, invoice.failure = "retry", "issuer unavailable"
        else:
            raise RuntimeError(f"unexpected paysafe response code {response.rc!r}")
        invoice.last_response = response
        return invoice
