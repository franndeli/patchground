"""Architecture checks: a pure domain core, storage and presentation at the edges."""

import ast
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "reports"


def loaded_by(module: str) -> set[str]:
    """Every module that importing ``module`` loads, directly or transitively, in a fresh interpreter."""
    code = f"import sys, {module}; print(chr(10).join(sys.modules))"
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=SRC.parents[1], env={"PYTHONPATH": "src"},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    return set(result.stdout.split())


def test_domain_depends_on_nothing_outside_itself():
    assert not loaded_by("reports.domain") & {"sqlite3", "reports.storage", "reports.text", "reports.report"}


def test_presentation_does_not_reach_storage():
    assert not loaded_by("reports.text") & {"sqlite3", "reports.storage", "reports.report"}


def test_storage_does_not_format():
    assert not loaded_by("reports.storage") & {"reports.text", "reports.report"}


SQL = re.compile(r"\bSELECT\b[\s\S]+\bFROM\b")  # SQL keywords as written in queries, not prose


def test_report_only_composes_the_layers():
    tree = ast.parse((SRC / "report.py").read_text(encoding="utf-8"))
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert "sqlite3" not in imports
    strings = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    assert not any(SQL.search(text) for text in strings)


def test_summarize_needs_no_database():
    from reports.domain import MonthlySummary, ProductLine, Sale, summarize

    summary = summarize("2026-07", [Sale("pen", 10, 150), Sale("ink", 2, 900), Sale("pen", -2, 150), Sale("cap", 6, 300)])
    assert summary == MonthlySummary(
        month="2026-07",
        lines=(ProductLine("cap", 1800), ProductLine("ink", 1800), ProductLine("pen", 1200)),
        refunds_cents=300,
        total_cents=4800,
    )


def test_summarize_keeps_net_negative_skus_and_empty_months():
    from reports.domain import ProductLine, Sale, summarize

    summary = summarize("2026-07", [Sale("mug", 1, 500), Sale("mug", -2, 500)])
    assert summary.lines == (ProductLine("mug", -500),)
    assert (summary.refunds_cents, summary.total_cents) == (1000, -500)
    empty = summarize("2026-08", [])
    assert (empty.lines, empty.refunds_cents, empty.total_cents) == ((), 0, 0)


def test_summarize_rejects_a_malformed_month():
    from reports.domain import summarize

    for month in ("2026-13", "26-01", "July"):
        with pytest.raises(ValueError):
            summarize(month, [])


def test_render_formats_any_summary():
    from reports.domain import MonthlySummary, ProductLine
    from reports.text import render

    summary = MonthlySummary("2026-07", (ProductLine("mug", 1050), ProductLine("tea", -5)), 205, 1045)
    assert render(summary) == (
        "Sales report 2026-07\n"
        "mug              10.50\n"
        "tea              -0.05\n"
        "Refunds           2.05\n"
        "Total            10.45\n"
    )
    assert render(MonthlySummary("2026-08", (), 0, 0)) == "Sales report 2026-08\nNo sales.\n"


def seed(path: Path, rows: list[tuple[str, int, int, str]]) -> str:
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE sales (id INTEGER PRIMARY KEY, sku TEXT, quantity INTEGER, unit_cents INTEGER, sold_on TEXT)"
    )
    connection.executemany("INSERT INTO sales (sku, quantity, unit_cents, sold_on) VALUES (?, ?, ?, ?)", rows)
    connection.commit()
    connection.close()
    return str(path)


def test_storage_returns_domain_sales_in_insertion_order(tmp_path):
    from reports.domain import Sale
    from reports.storage import SqliteSales

    db = seed(tmp_path / "s.db", [("b", 1, 100, "2026-02-03"), ("a", 2, 50, "2026-02-01"), ("c", 1, 1, "2026-03-01")])
    assert list(SqliteSales(db).for_month("2026-02")) == [Sale("b", 1, 100), Sale("a", 2, 50)]


def test_report_is_the_composition_of_the_layers(tmp_path):
    from reports.domain import summarize
    from reports.report import monthly_report
    from reports.storage import SqliteSales
    from reports.text import render

    db = seed(tmp_path / "s.db", [("mug", 1, 500, "2026-07-01"), ("mug", -2, 500, "2026-07-02"), ("tea", 3, 333, "2026-07-03")])
    expected = render(summarize("2026-07", SqliteSales(db).for_month("2026-07")))
    assert monthly_report(db, "2026-07") == expected
    assert expected.splitlines()[1:] == ["tea               9.99", "mug              -5.00", "Refunds          10.00", "Total             4.99"]
