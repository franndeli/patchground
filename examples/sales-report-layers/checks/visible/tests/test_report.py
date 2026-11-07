import os

import pytest

from reports.report import monthly_report


def test_march_report(sales_db):
    assert monthly_report(sales_db, "2026-03") == (
        "Sales report 2026-03\n"
        "desk            398.00\n"
        "chair           356.00\n"
        "lamp             49.00\n"
        "Refunds          24.50\n"
        "Total           803.00\n"
    )


def test_month_without_sales(sales_db):
    assert monthly_report(sales_db, "2026-05") == "Sales report 2026-05\nNo sales.\n"


def test_bad_month_is_rejected_before_opening_the_database(tmp_path):
    missing = tmp_path / "nowhere.db"
    with pytest.raises(ValueError):
        monthly_report(str(missing), "March")
    assert not os.path.exists(missing)
