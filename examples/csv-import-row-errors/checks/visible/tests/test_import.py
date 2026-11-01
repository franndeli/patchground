import pytest

from stockimport import ImportFailed, ImportResult, Item, RowError, import_inventory

HEADER = "sku,quantity,unit_price"


def doc(*lines):
    return "\n".join((HEADER, *lines)) + "\n"


def test_strict_returns_items_in_file_order():
    items = import_inventory(doc("A-1,5,19.99", "B-1,2,0.29"))
    assert items == [Item("A-1", 5, 1999), Item("B-1", 2, 29)]


def test_strict_default_raises_the_first_error():
    with pytest.raises(ImportFailed) as caught:
        import_inventory(doc("A-1,5,19.99", "A-2,1,x", "A-3,y,1.00"))
    assert (caught.value.error.line, caught.value.error.code) == (3, "invalid_price")
    assert isinstance(caught.value, ValueError)


def test_result_types_have_the_documented_fields():
    error = RowError(2, "sku", "invalid_sku", "bad")
    result = ImportResult([Item("A", 1, 100)], [error])
    assert result.items == [Item("A", 1, 100)]
    assert (error.line, error.column, error.code) == (2, "sku", "invalid_sku")


def test_non_strict_returns_valid_items_and_row_errors():
    result = import_inventory(doc("A-1,5,19.99", "A-2,x,1.00", "B-1,2,0.29"), strict=False)
    assert result.items == [Item("A-1", 5, 1999), Item("B-1", 2, 29)]
    assert [(e.line, e.column, e.code) for e in result.errors] == [(3, "quantity", "invalid_quantity")]
