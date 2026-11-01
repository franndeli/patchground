"""Strict CSV import for the warehouse stock feed."""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterator

from .models import ImportFailed, Item, RowError

HEADER = ["sku", "quantity", "unit_price"]

_SKU = re.compile(r"[A-Z0-9-]+")
_QUANTITY = re.compile(r"[0-9]+")
_PRICE = re.compile(r"([0-9]+)(?:\.([0-9]{1,2}))?")


def _fail(line: int, column: str | None, code: str, message: str) -> ImportFailed:
    return ImportFailed(RowError(line, column, code, message))


def import_inventory(text: str) -> list[Item]:
    """Parse ``text`` and return its items in file order.

    The first problem found stops the import with ``ImportFailed``.
    """
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    _read_header(reader)
    items: list[Item] = []
    seen: set[str] = set()
    while True:
        line = reader.line_num + 1  # physical line where the next record starts
        try:
            record = next(reader)
        except StopIteration:
            return items
        except csv.Error as exc:
            raise _fail(line, None, "malformed_csv", str(exc)) from None
        if record:  # a physical line with no characters yields []
            items.append(_parse_record(record, line, seen))


def _read_header(reader: Iterator[list[str]]) -> None:
    try:
        header = next(reader)
    except (StopIteration, csv.Error):
        header = None
    if header != HEADER:
        raise _fail(1, None, "bad_header", "header must be exactly sku,quantity,unit_price")


def _parse_record(record: list[str], line: int, seen: set[str]) -> Item:
    if len(record) != 3:
        raise _fail(line, None, "wrong_field_count", f"expected 3 fields, got {len(record)}")
    sku, quantity, price = record
    if not _SKU.fullmatch(sku):
        raise _fail(line, "sku", "invalid_sku", f"invalid sku {sku!r}")
    if sku in seen:
        raise _fail(line, "sku", "duplicate_sku", f"duplicate sku {sku!r}")
    seen.add(sku)
    if not _QUANTITY.fullmatch(quantity):
        raise _fail(line, "quantity", "invalid_quantity", f"invalid quantity {quantity!r}")
    match = _PRICE.fullmatch(price)
    if match is None:
        raise _fail(line, "unit_price", "invalid_price", f"invalid unit_price {price!r}")
    dollars, fraction = match.groups()
    cents = int(dollars) * 100 + int((fraction or "").ljust(2, "0"))
    return Item(sku, int(quantity), cents)
