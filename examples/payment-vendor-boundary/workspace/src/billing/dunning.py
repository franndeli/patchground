"""What to do next about an invoice that has not been paid."""

from __future__ import annotations

from billing.invoices import Invoice


def next_action(invoice: Invoice) -> str:
    if invoice.status == "paid":
        return "none"
    if invoice.status == "open":
        return "collect"
    if invoice.status == "retry":
        return "retry in 1 hour"
    if invoice.last_response is not None and invoice.last_response.rc == "51":
        return "email: top up and retry in 3 days"
    return "email: update card"
