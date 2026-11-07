"""The monthly sales report: read the month's sales, total them, print them."""

from __future__ import annotations

import re
import sqlite3

MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])")


def money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def monthly_report(db_path: str, month: str) -> str:
    """Plain-text report of net sales per SKU for one month (``YYYY-MM``)."""
    if not MONTH.fullmatch(month):
        raise ValueError(f"month must look like 2026-03, got {month!r}")

    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            "SELECT sku, quantity, unit_cents FROM sales WHERE substr(sold_on, 1, 7) = ? ORDER BY id",
            (month,),
        ).fetchall()
    finally:
        connection.close()

    net_by_sku: dict[str, int] = {}
    refunds = 0
    for sku, quantity, unit_cents in rows:
        amount = quantity * unit_cents
        if quantity < 0:
            refunds += -amount
        net_by_sku[sku] = net_by_sku.get(sku, 0) + amount

    lines = [f"Sales report {month}"]
    if not net_by_sku:
        lines.append("No sales.")
        return "\n".join(lines) + "\n"
    for sku, net in sorted(net_by_sku.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"{sku:<12}{money(net):>10}")
    lines.append(f"{'Refunds':<12}{money(refunds):>10}")
    lines.append(f"{'Total':<12}{money(sum(net_by_sku.values())):>10}")
    return "\n".join(lines) + "\n"
