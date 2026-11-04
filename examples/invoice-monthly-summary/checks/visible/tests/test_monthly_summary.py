import pytest

from invoices.database import create_database
from invoices.demo import build_preview_database
from invoices.repository import InvoiceRepository, MonthlyTotal


@pytest.fixture
def database():
    connection = create_database()
    yield connection
    connection.close()


def add_invoice(connection, invoice_id, issued_at, amounts, status="issued", org="harbor"):
    connection.execute(
        "INSERT INTO invoices VALUES (?, ?, ?, ?)",
        (org, invoice_id, issued_at, status),
    )
    connection.executemany(
        "INSERT INTO invoice_lines VALUES (?, ?, ?, ?)",
        [(org, invoice_id, str(index), amount) for index, amount in enumerate(amounts)],
    )


def test_public_preview_keeps_years_distinct_and_sums_lines_once():
    connection = build_preview_database()
    try:
        assert InvoiceRepository(connection).monthly_summary(
            "harbor", "2024-01-01T00:00:00Z", "2026-01-01T00:00:00Z"
        ) == [
            MonthlyTotal("2024-01", 1200),
            MonthlyTotal("2025-01", 325),
            MonthlyTotal("2025-02", 0),
        ]
    finally:
        connection.close()


def test_several_lines_contribute_once(database):
    add_invoice(database, "usage", "2025-06-12T00:00:00Z", [120, 80, -30])
    assert InvoiceRepository(database).monthly_summary(
        "harbor", "2025-06-01T00:00:00Z", "2025-07-01T00:00:00Z"
    ) == [MonthlyTotal("2025-06", 170)]


def test_interval_includes_start_and_excludes_end(database):
    add_invoice(database, "start", "2025-05-01T00:00:00Z", [200])
    add_invoice(database, "end", "2025-06-01T00:00:00Z", [900])
    assert InvoiceRepository(database).monthly_summary(
        "harbor", "2025-05-01T00:00:00Z", "2025-06-01T00:00:00Z"
    ) == [MonthlyTotal("2025-05", 200)]


def test_zero_line_invoice_keeps_its_month(database):
    add_invoice(database, "empty", "2025-09-10T00:00:00Z", [])
    assert InvoiceRepository(database).monthly_summary(
        "harbor", "2025-01-01T00:00:00Z", "2026-01-01T00:00:00Z"
    ) == [MonthlyTotal("2025-09", 0)]


def test_status_and_organization_filters(database):
    add_invoice(database, "shared", "2025-08-01T00:00:00Z", [250])
    add_invoice(database, "shared", "2025-08-01T00:00:00Z", [999], org="neighbor")
    add_invoice(database, "draft", "2025-09-01T00:00:00Z", [1000], status="draft")
    add_invoice(database, "void", "2025-10-01T00:00:00Z", [1000], status="void")
    assert InvoiceRepository(database).monthly_summary(
        "harbor", "2025-01-01T00:00:00Z", "2026-01-01T00:00:00Z"
    ) == [MonthlyTotal("2025-08", 250)]


def test_no_qualifying_invoices_returns_empty_sequence(database):
    assert InvoiceRepository(database).monthly_summary(
        "harbor", "2025-01-01T00:00:00Z", "2026-01-01T00:00:00Z"
    ) == []


def test_large_amounts_can_cancel_to_a_valid_integer_total(database):
    largest = 2**63 - 1
    add_invoice(
        database, "cancellation", "2025-06-12T00:00:00Z", [largest, 1, -largest]
    )
    result = InvoiceRepository(database).monthly_summary(
        "harbor", "2025-06-01T00:00:00Z", "2025-07-01T00:00:00Z"
    )
    assert result == [MonthlyTotal("2025-06", 1)]
    assert type(result[0].total_cents) is int
