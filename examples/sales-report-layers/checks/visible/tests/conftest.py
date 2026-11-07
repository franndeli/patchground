import sqlite3

import pytest


@pytest.fixture
def sales_db(tmp_path):
    path = tmp_path / "sales.db"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE sales (id INTEGER PRIMARY KEY, sku TEXT, quantity INTEGER, unit_cents INTEGER, sold_on TEXT)"
    )
    connection.executemany(
        "INSERT INTO sales (sku, quantity, unit_cents, sold_on) VALUES (?, ?, ?, ?)",
        [
            ("desk", 2, 19900, "2026-03-02"),
            ("lamp", 3, 2450, "2026-03-04"),
            ("chair", 4, 8900, "2026-03-09"),
            ("lamp", -1, 2450, "2026-03-15"),
            ("desk", 1, 19900, "2026-04-01"),
        ],
    )
    connection.commit()
    connection.close()
    return str(path)
