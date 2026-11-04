# Monthly invoice totals are wrong

The billing dashboard shows one January row for a report spanning two years.
An invoice with several lines also inflates its month's total. Finance needs
the report fixed before using it for the next export.

Repair `InvoiceRepository.monthly_summary(organization_id, start, end)` in
`src/invoices/repository.py`. Keep database access behind this existing interface.
Add regression checks under `tests/`. You may use SQL or Python within the
repository. No particular query or performance threshold is required.

## Supplied interface and data

Import `InvoiceRepository` and `MonthlyTotal` from `invoices.repository`.
Construct the repository with an existing `sqlite3.Connection`. The method
returns `list[MonthlyTotal]`, where the frozen dataclass has `month: str` and
`total_cents: int`.

`invoices.database.create_database()` creates an empty, in-memory SQLite database.
The caller owns the connection. `invoices.demo.build_preview_database()` provides
a deterministic, public sample dataset. Checks create fixtures inside Docker
using Python's built-in SQLite. No service or download is needed at check time.

The supplied schema has these columns:

- `invoices(organization_id, invoice_id, issued_at, status)`. The primary key is
  `(organization_id, invoice_id)`. Status is `issued`, `draft` or `void`.
- `invoice_lines(organization_id, invoice_id, line_id, amount_cents)`. The primary
  key is `(organization_id, invoice_id, line_id)`. Its composite foreign key
  identifies the parent invoice. Invoice IDs and line IDs may repeat in other
  organizations.

Every timestamp, including `start` and `end`, uses UTC ISO text in exactly
`YYYY-MM-DDTHH:MM:SSZ` form. Inputs are prevalidated and `start <= end`. Money
is an integer number of cents. Credit lines may be negative. Assume totals fit
SQLite's signed 64-bit integer range. Do not add currency conversion, floating-point
money, timestamp parsing or input validation.

## Required behavior

- Select only the requested organization's invoices with status `issued`.
  Draft and void invoices do not contribute a month or an amount.
- Include an invoice when `start <= issued_at < end`. The lower boundary is
  inclusive and the upper boundary is exclusive.
- Group by both year and month. Return ascending `YYYY-MM` rows, with exactly
  one row per month containing a qualifying invoice.
- Sum each qualifying line item once, including equal-valued lines and negative
  credit lines. Keep amounts as integers.
- An issued invoice with no lines contributes zero and still creates its month.
  Keep a month whose total is zero or negative.
- Omit months with no qualifying invoices. An empty result, including an empty
  interval, returns `[]`.
- Keep organizations isolated, even when invoice IDs overlap.
- The report is read-only. Do not modify stored invoices or lines, and leave the
  caller's connection open for subsequent reports.

The preview dataset for organization `harbor`, from `2024-01-01T00:00:00Z` up to
`2026-01-01T00:00:00Z`, must return:

```python
[
    MonthlyTotal("2024-01", 1200),
    MonthlyTotal("2025-01", 325),
    MonthlyTotal("2025-02", 0),
]
```

Use Patchground checks in Docker, not host Python or pytest. Keep the schema,
fixtures and public interface intact. No additional dependencies are needed.

This original Patchground challenge is AI-generated. Its intermediate difficulty
and 45-minute timebox are estimates, not human-calibrated measurements.
