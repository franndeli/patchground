"""Deterministic SQLite setup shared by the preview and repository callers."""

import sqlite3


def create_database() -> sqlite3.Connection:
    """Create an empty database. The caller owns and closes the connection."""
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript("""
        CREATE TABLE invoices (
            organization_id TEXT NOT NULL,
            invoice_id TEXT NOT NULL,
            issued_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('issued', 'draft', 'void')),
            PRIMARY KEY (organization_id, invoice_id)
        );
        CREATE TABLE invoice_lines (
            organization_id TEXT NOT NULL,
            invoice_id TEXT NOT NULL,
            line_id TEXT NOT NULL,
            amount_cents INTEGER NOT NULL,
            PRIMARY KEY (organization_id, invoice_id, line_id),
            FOREIGN KEY (organization_id, invoice_id)
                REFERENCES invoices (organization_id, invoice_id)
        );
    """)
    return connection
