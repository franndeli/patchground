"""Composition root: the one place that builds the billing services."""

from __future__ import annotations

from billing.invoices import InvoiceService
from paysafe import PaysafeClient


def build_invoice_service(client: PaysafeClient) -> InvoiceService:
    return InvoiceService(client)
