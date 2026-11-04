import pytest

from invoices.database import create_database
from invoices.repository import InvoiceRepository, MonthlyTotal


@pytest.fixture
def ledger():
    connection = create_database()
    yield connection
    connection.close()


def insert(connection, org, invoice_id, timestamp, amounts=(), status="issued"):
    connection.execute(
        "INSERT INTO invoices VALUES (?, ?, ?, ?)",
        (org, invoice_id, timestamp, status),
    )
    connection.executemany(
        "INSERT INTO invoice_lines VALUES (?, ?, ?, ?)",
        [(org, invoice_id, str(n), amount) for n, amount in enumerate(amounts)],
    )


def test_year_month_grouping_and_chronological_order(ledger):
    insert(ledger, "north", "later", "2026-01-30T23:59:59Z", [11])
    insert(ledger, "north", "earliest", "2024-12-31T23:59:59Z", [7])
    insert(ledger, "north", "jan", "2025-01-01T00:00:00Z", [13])
    insert(ledger, "north", "dec", "2025-12-03T00:00:00Z", [19])
    assert InvoiceRepository(ledger).monthly_summary(
        "north", "2024-01-01T00:00:00Z", "2027-01-01T00:00:00Z"
    ) == [
        MonthlyTotal("2024-12", 7), MonthlyTotal("2025-01", 13),
        MonthlyTotal("2025-12", 19), MonthlyTotal("2026-01", 11),
    ]


def test_equal_line_values_and_invoice_totals_are_not_deduplicated(ledger):
    insert(ledger, "north", "a", "2025-02-02T00:00:00Z", [200, 200])
    insert(ledger, "north", "b", "2025-02-20T00:00:00Z", [400])
    insert(ledger, "north", "c", "2025-02-21T00:00:00Z", [-50, -50, 100])
    assert InvoiceRepository(ledger).monthly_summary(
        "north", "2025-02-01T00:00:00Z", "2025-03-01T00:00:00Z"
    ) == [MonthlyTotal("2025-02", 800)]


def test_neighbor_with_same_invoice_and_line_ids_cannot_affect_totals(ledger):
    insert(ledger, "north", "shared", "2025-04-01T00:00:00Z", [3, 8])
    insert(ledger, "south", "shared", "2025-04-01T00:00:00Z", [700, 900])
    insert(ledger, "south", "foreign-only", "2025-05-01T00:00:00Z", [100])
    repo = InvoiceRepository(ledger)
    assert repo.monthly_summary(
        "north", "2025-01-01T00:00:00Z", "2026-01-01T00:00:00Z"
    ) == [MonthlyTotal("2025-04", 11)]
    assert repo.monthly_summary(
        "south", "2025-01-01T00:00:00Z", "2026-01-01T00:00:00Z"
    ) == [MonthlyTotal("2025-04", 1600), MonthlyTotal("2025-05", 100)]


def test_submonth_interval_is_half_open(ledger):
    insert(ledger, "north", "before", "2025-07-12T12:29:59Z", [901])
    insert(ledger, "north", "start", "2025-07-12T12:30:00Z", [17])
    insert(ledger, "north", "last", "2025-07-12T13:29:59Z", [23])
    insert(ledger, "north", "end", "2025-07-12T13:30:00Z", [902])
    insert(ledger, "north", "after", "2025-07-12T13:30:01Z", [903])
    assert InvoiceRepository(ledger).monthly_summary(
        "north", "2025-07-12T12:30:00Z", "2025-07-12T13:30:00Z"
    ) == [MonthlyTotal("2025-07", 40)]


def test_empty_interval_at_an_existing_invoice_returns_no_rows(ledger):
    insert(ledger, "north", "at-boundary", "2025-06-01T00:00:00Z", [41])
    assert InvoiceRepository(ledger).monthly_summary(
        "north", "2025-06-01T00:00:00Z", "2025-06-01T00:00:00Z"
    ) == []


def test_only_issued_invoices_create_month_buckets(ledger):
    insert(ledger, "north", "draft", "2025-01-01T00:00:00Z", [500], "draft")
    insert(ledger, "north", "void", "2025-02-01T00:00:00Z", [600], "void")
    insert(ledger, "north", "issued-empty", "2025-03-01T00:00:00Z")
    insert(ledger, "north", "draft-same-month", "2025-03-02T00:00:00Z", [700], "draft")
    insert(ledger, "north", "void-empty", "2025-04-01T00:00:00Z", (), "void")
    assert InvoiceRepository(ledger).monthly_summary(
        "north", "2025-01-01T00:00:00Z", "2026-01-01T00:00:00Z"
    ) == [MonthlyTotal("2025-03", 0)]


def test_zero_and_negative_months_are_retained(ledger):
    insert(ledger, "north", "empty-a", "2025-10-01T00:00:00Z")
    insert(ledger, "north", "empty-b", "2025-10-02T00:00:00Z")
    insert(ledger, "north", "offset", "2025-11-01T00:00:00Z", [300, -300])
    insert(ledger, "north", "credit", "2025-12-01T00:00:00Z", [-80, -20])
    assert InvoiceRepository(ledger).monthly_summary(
        "north", "2025-01-01T00:00:00Z", "2026-01-01T00:00:00Z"
    ) == [
        MonthlyTotal("2025-10", 0), MonthlyTotal("2025-11", 0),
        MonthlyTotal("2025-12", -100),
    ]


def test_large_integer_cents_remain_exact(ledger):
    insert(ledger, "north", "large", "2025-08-01T00:00:00Z", [9007199254740993, 2, -1])
    result = InvoiceRepository(ledger).monthly_summary(
        "north", "2025-08-01T00:00:00Z", "2025-09-01T00:00:00Z"
    )
    assert result == [MonthlyTotal("2025-08", 9007199254740994)]
    assert type(result[0].total_cents) is int


def test_empty_database_and_unknown_organization_return_empty(ledger):
    repo = InvoiceRepository(ledger)
    assert repo.monthly_summary(
        "missing", "2025-01-01T00:00:00Z", "2026-01-01T00:00:00Z"
    ) == []
    insert(ledger, "north", "existing", "2025-01-01T00:00:00Z", [5])
    assert repo.monthly_summary(
        "missing", "2025-01-01T00:00:00Z", "2026-01-01T00:00:00Z"
    ) == []


def test_reporting_is_read_only_and_connection_is_reusable(ledger):
    insert(ledger, "north", "a", "2025-05-01T00:00:00Z", [23])
    ledger.commit()
    before = list(ledger.iterdump())
    repo = InvoiceRepository(ledger)
    for _ in range(2):
        assert repo.monthly_summary(
            "north", "2025-01-01T00:00:00Z", "2026-01-01T00:00:00Z"
        ) == [MonthlyTotal("2025-05", 23)]
    assert list(ledger.iterdump()) == before


def test_large_credits_cancel_across_invoices_without_overflow(ledger):
    largest = 2**63 - 1
    insert(ledger, "north", "a", "2025-09-01T00:00:00Z", [-largest])
    insert(ledger, "north", "b", "2025-09-02T00:00:00Z", [-2])
    insert(ledger, "north", "c", "2025-09-03T00:00:00Z", [largest])
    result = InvoiceRepository(ledger).monthly_summary(
        "north", "2025-09-01T00:00:00Z", "2025-10-01T00:00:00Z"
    )
    assert result == [MonthlyTotal("2025-09", -2)]
    assert type(result[0].total_cents) is int
