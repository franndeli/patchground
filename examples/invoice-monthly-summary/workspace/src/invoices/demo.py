"""Public preview data, rebuilt in memory without clocks or external services."""

import sqlite3

from invoices.database import create_database


def build_preview_database() -> sqlite3.Connection:
    """Create the small dataset described in the ticket."""
    connection = create_database()
    connection.executemany(
        "INSERT INTO invoices VALUES (?, ?, ?, ?)",
        [
            ("harbor", "annual-24", "2024-01-10T09:00:00Z", "issued"),
            ("harbor", "annual-25", "2025-01-10T09:00:00Z", "issued"),
            ("harbor", "credit-25", "2025-01-21T12:00:00Z", "issued"),
            ("harbor", "empty-25", "2025-02-01T00:00:00Z", "issued"),
            ("harbor", "draft-25", "2025-03-01T00:00:00Z", "draft"),
            ("harbor", "void-25", "2025-04-01T00:00:00Z", "void"),
            ("neighbor", "annual-25", "2025-01-10T09:00:00Z", "issued"),
        ],
    )
    connection.executemany(
        "INSERT INTO invoice_lines VALUES (?, ?, ?, ?)",
        [
            ("harbor", "annual-24", "base", 1000),
            ("harbor", "annual-24", "usage", 200),
            ("harbor", "annual-25", "base", 300),
            ("harbor", "annual-25", "usage", 100),
            ("harbor", "credit-25", "adjustment", -75),
            ("harbor", "draft-25", "base", 9000),
            ("harbor", "void-25", "base", 7000),
            ("neighbor", "annual-25", "base", 8000),
        ],
    )
    connection.commit()
    return connection
