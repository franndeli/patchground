"""Read monthly invoice amounts for the billing dashboard."""

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class MonthlyTotal:
    month: str
    total_cents: int


class InvoiceRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def monthly_summary(
        self, organization_id: str, start: str, end: str
    ) -> list[MonthlyTotal]:
        """Return issued invoice totals in a UTC reporting interval."""
        rows = self.connection.execute(
            """
            WITH invoice_totals AS (
                SELECT organization_id, invoice_id, SUM(amount_cents) AS total_cents
                FROM invoice_lines
                GROUP BY organization_id, invoice_id
            )
            SELECT substr(i.issued_at, 1, 7) AS month,
                   SUM(t.total_cents) AS total_cents
            FROM invoices AS i
            JOIN invoice_totals AS t
              ON t.organization_id = i.organization_id
             AND t.invoice_id = i.invoice_id
            JOIN invoice_lines AS l
              ON l.organization_id = i.organization_id
             AND l.invoice_id = i.invoice_id
            WHERE i.organization_id = ?
              AND i.status = 'issued'
              AND i.issued_at >= ?
              AND i.issued_at <= ?
            GROUP BY strftime('%m', i.issued_at)
            ORDER BY month
            """,
            (organization_id, start, end),
        )
        return [MonthlyTotal(month, total_cents) for month, total_cents in rows]
