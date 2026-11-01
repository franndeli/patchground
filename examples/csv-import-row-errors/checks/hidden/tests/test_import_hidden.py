"""Hidden checks. Each group names the TICKET rule it covers."""

import pytest

from stockimport import ImportFailed, ImportResult, Item, RowError, import_inventory

HEADER = "sku,quantity,unit_price"


def doc(*lines, end="\n"):
    return "\n".join((HEADER, *lines)) + end


def lenient(text):
    return import_inventory(text, strict=False)


def shape(errors):
    return [(e.line, e.column, e.code) for e in errors]


def strict_error(text):
    with pytest.raises(ImportFailed) as caught:
        import_inventory(text)
    assert isinstance(caught.value.error, RowError)
    return caught.value.error


# --- Public API -------------------------------------------------------------------------------


def test_api_non_strict_returns_import_result_with_lists():
    result = lenient(doc("A-1,1,1.00"))
    assert isinstance(result, ImportResult)
    assert isinstance(result.items, list) and isinstance(result.errors, list)
    assert result.items == [Item("A-1", 1, 100)]
    assert result.errors == []


def test_api_default_and_explicit_strict_return_a_plain_list():
    text = doc("A-1,1,1.00", "B-2,3,2.50")
    expected = [Item("A-1", 1, 100), Item("B-2", 3, 250)]
    assert import_inventory(text) == expected
    assert import_inventory(text, strict=True) == expected


def test_api_strict_is_keyword_only():
    with pytest.raises(TypeError):
        import_inventory(doc("A-1,1,1.00"), False)


def test_api_import_failed_text_and_type():
    with pytest.raises(ValueError, match=r"^line 2: ") as caught:
        import_inventory(doc("A-1,x,1.00"))
    assert isinstance(caught.value, ImportFailed)
    assert caught.value.error.line == 2


# --- Rule 1: header -----------------------------------------------------------------------------

BAD_HEADERS = [
    pytest.param("", id="empty-text"),
    pytest.param("\n", id="blank-first-line"),
    pytest.param("\nsku,quantity,unit_price\nA-1,1,1.00\n", id="blank-then-header"),
    pytest.param("sku,quantity\nA-1,1\n", id="missing-column"),
    pytest.param("sku,quantity,unit_price,extra\nA-1,1,1.00,x\n", id="extra-column"),
    pytest.param("sku,qty,unit_price\nA-1,1,1.00\n", id="renamed-column"),
    pytest.param("quantity,sku,unit_price\n1,A-1,1.00\n", id="reordered"),
    pytest.param("SKU,quantity,unit_price\nA-1,1,1.00\n", id="case-sensitive"),
    pytest.param(" sku,quantity,unit_price\nA-1,1,1.00\n", id="not-trimmed"),
]


@pytest.mark.parametrize("text", BAD_HEADERS)
@pytest.mark.parametrize("strict", [True, False])
def test_rule1_bad_header_fails_in_both_modes(text, strict):
    with pytest.raises(ImportFailed) as caught:
        import_inventory(text, strict=strict)
    error = caught.value.error
    assert (error.line, error.column, error.code) == (1, None, "bad_header")


def test_rule1_header_only_and_crlf_header_are_valid():
    assert lenient(HEADER + "\n") == ImportResult([], [])
    assert lenient(HEADER) == ImportResult([], [])
    result = lenient(HEADER + "\r\nA-1,2,3.00\r\n")
    assert result.items == [Item("A-1", 2, 300)] and result.errors == []


# --- Rule 2: malformed CSV ----------------------------------------------------------------------


def test_rule2_unterminated_quote_reports_the_record_start_line():
    text = doc("A-1,1,1.00", 'A-2,"5,1.00', "A-3,1,1.00")
    for strict in (True, False):
        with pytest.raises(ImportFailed) as caught:
            import_inventory(text, strict=strict)
        error = caught.value.error
        assert (error.line, error.column, error.code) == (3, None, "malformed_csv")


def test_rule2_text_after_closing_quote_after_a_multiline_record():
    text = doc('"A\nB",1,1.00', '"A-1"x,1,1.00')
    # header = 1, multi-line record = lines 2-3, the broken record starts on line 4
    with pytest.raises(ImportFailed) as caught:
        lenient(text)
    error = caught.value.error
    assert (error.line, error.column, error.code) == (4, None, "malformed_csv")


def test_rule2_non_strict_returns_no_partial_result():
    text = doc("A-1,1,1.00", "B-2,x,1.00", '"C-3"junk,1,1.00')
    with pytest.raises(ImportFailed) as caught:
        lenient(text)
    assert caught.value.error.code == "malformed_csv"


def test_rule2_strict_reports_an_earlier_row_error_before_the_syntax_error():
    text = doc("A-1,1,1.00", "B-2,x,1.00", '"C-3"junk,1,1.00')
    error = strict_error(text)
    assert (error.line, error.code) == (3, "invalid_quantity")


# --- Rule 3: empty lines ------------------------------------------------------------------------


def test_rule3_empty_lines_are_skipped_but_counted():
    text = doc("A-1,1,1.00", "", "", "B-2,x,1.00", "", "C-3,1,1.00", "", end="\n\n")
    result = lenient(text)
    assert [i.sku for i in result.items] == ["A-1", "C-3"]
    assert shape(result.errors) == [(5, "quantity", "invalid_quantity")]


def test_rule3_crlf_empty_lines_are_skipped_and_counted():
    text = HEADER + "\r\n\r\nA-1,x,1.00\r\n\r\nB-2,1,1.00\r\n"
    result = lenient(text)
    assert [i.sku for i in result.items] == ["B-2"]
    assert shape(result.errors) == [(3, "quantity", "invalid_quantity")]


@pytest.mark.parametrize("line", [" ", '""', "\t"], ids=repr)
def test_rule3_lines_that_are_not_empty_are_records(line):
    result = lenient(doc("A-1,1,1.00", line))
    assert shape(result.errors) == [(3, None, "wrong_field_count")]


# --- Rules 4 and 5: one error per row, check order ----------------------------------------------


def test_rule5_wrong_field_count_wins_over_everything():
    result = lenient(doc("a b,1", "A-1,1,1.00,extra", "A-2"))
    assert shape(result.errors) == [
        (2, None, "wrong_field_count"),
        (3, None, "wrong_field_count"),
        (4, None, "wrong_field_count"),
    ]
    assert result.items == []


ORDER_CASES = [
    pytest.param(["bad sku,x,y"], "invalid_sku", "sku", id="sku-before-quantity-and-price"),
    pytest.param(["A-1,1,1.00", "A-1,x,y"], "duplicate_sku", "sku", id="duplicate-before-quantity"),
    pytest.param(["A-1,1,1.00", "A-1,1,y"], "duplicate_sku", "sku", id="duplicate-before-price"),
    pytest.param(["A-1,x,y"], "invalid_quantity", "quantity", id="quantity-before-price"),
    pytest.param(["A-1,1,y"], "invalid_price", "unit_price", id="price-last"),
]


@pytest.mark.parametrize(("rows", "code", "column"), ORDER_CASES)
def test_rule5_each_row_gets_only_its_first_failing_check(rows, code, column):
    result = lenient(doc(*rows))
    assert len(result.errors) == 1
    assert (result.errors[0].code, result.errors[0].column) == (code, column)
    assert result.errors[0].line == len(rows) + 1


@pytest.mark.parametrize("sku", ["", "a-1", "A 1", " A-1", "A-1 ", "A_1", "É-1", "A\n1"], ids=repr)
def test_rule5_invalid_sku(sku):
    text = HEADER + "\n" + '"' + sku + '"' + ",1,1.00\n"
    result = lenient(text)
    assert result.items == []
    assert shape(result.errors) == [(2, "sku", "invalid_sku")]


@pytest.mark.parametrize("sku", ["A", "0", "-", "AB-12-C", "007"], ids=repr)
def test_rule5_valid_sku(sku):
    assert lenient(doc(f"{sku},1,1.00")).items == [Item(sku, 1, 100)]


@pytest.mark.parametrize("quantity", ["", "-1", "+2", "1.5", "1e2", " 3", "3 ", "٣", "１２", "0x10"], ids=repr)
def test_rule5_invalid_quantity(quantity):
    text = HEADER + "\n" + 'A-1,"' + quantity + '",1.00\n'
    assert shape(lenient(text).errors) == [(2, "quantity", "invalid_quantity")]


@pytest.mark.parametrize(("quantity", "value"), [("0", 0), ("7", 7), ("007", 7), ("1000000", 1000000)], ids=repr)
def test_rule5_valid_quantity(quantity, value):
    assert lenient(doc(f"A-1,{quantity},1.00")).items == [Item("A-1", value, 100)]


BAD_PRICES = ["", ".5", "5.", "12.345", "-1", "+1", "1e3", "1,000.00", " 1", "1 ", "1.0.0", "NaN", "inf", "١٢", "1.٥", "$1"]


@pytest.mark.parametrize("price", BAD_PRICES, ids=repr)
def test_rule5_invalid_price(price):
    text = HEADER + "\n" + 'A-1,1,"' + price + '"\n'
    result = lenient(text)
    assert result.items == []
    assert shape(result.errors) == [(2, "unit_price", "invalid_price")]


# --- Rule 6: exact cents ------------------------------------------------------------------------

CENTS = [
    ("0", 0),
    ("0.00", 0),
    ("12", 1200),
    ("12.5", 1250),
    ("12.50", 1250),
    ("12.05", 1205),
    ("0.1", 10),
    ("0.01", 1),
    ("0.29", 29),
    ("1.15", 115),
    ("19.99", 1999),
    ("4.35", 435),
    ("1234567.89", 123456789),
    ("90071992547409.93", 9007199254740993),
]


@pytest.mark.parametrize(("price", "cents"), CENTS, ids=repr)
def test_rule6_prices_become_exact_integer_cents(price, cents):
    (item,) = lenient(doc(f"A-1,1,{price}")).items
    assert item.unit_price_cents == cents
    assert type(item.unit_price_cents) is int


@pytest.mark.parametrize(("price", "cents"), CENTS, ids=repr)
def test_rule6_strict_and_non_strict_agree_on_cents(price, cents):
    assert import_inventory(doc(f"A-1,1,{price}")) == [Item("A-1", 1, cents)]


# --- Rule 7: duplicates -------------------------------------------------------------------------


def test_rule7_first_accepted_row_wins():
    result = lenient(doc("A-1,5,1.00", "A-1,9,9.00", "A-1,7,7.00"))
    assert result.items == [Item("A-1", 5, 100)]
    assert shape(result.errors) == [(3, "sku", "duplicate_sku"), (4, "sku", "duplicate_sku")]


@pytest.mark.parametrize(
    "bad_row",
    [
        pytest.param("A-1,x,1.00", id="bad-quantity"),
        pytest.param("A-1,1,1.005", id="bad-price"),
        pytest.param("A-1,1", id="wrong-field-count"),
        pytest.param("A-1,-1,x", id="both-bad"),
    ],
)
def test_rule7_a_rejected_row_does_not_reserve_its_sku(bad_row):
    result = lenient(doc(bad_row, "A-1,5,2.50"))
    assert result.items == [Item("A-1", 5, 250)]
    assert len(result.errors) == 1 and result.errors[0].line == 2


def test_rule7_a_multiline_rejected_row_does_not_reserve_its_sku():
    result = lenient(doc('A-1,"1\n2",1.00', "A-1,3,1.00"))
    assert result.items == [Item("A-1", 3, 100)]
    assert shape(result.errors) == [(2, "quantity", "invalid_quantity")]


def test_rule7_duplicates_ignore_blank_lines_between_rows():
    result = lenient(doc("A-1,1,1.00", "", "A-1,2,2.00"))
    assert result.items == [Item("A-1", 1, 100)]
    assert shape(result.errors) == [(4, "sku", "duplicate_sku")]


# --- Lines of multi-line records (rules in "Input format and line numbers") -----------------------


def test_lines_multiline_record_reports_its_start_and_shifts_later_lines():
    text = doc('"A\nB",1,1.00', "C-1,x,1.00", 'D-1,"1\n2\n3",1.00', "E-1,x,1.00")
    result = lenient(text)
    assert shape(result.errors) == [
        (2, "sku", "invalid_sku"),
        (4, "quantity", "invalid_quantity"),
        (5, "quantity", "invalid_quantity"),
        (8, "quantity", "invalid_quantity"),
    ]
    assert result.items == []


def test_lines_multiline_record_with_crlf():
    text = HEADER + '\r\n"A\r\nB",1,1.00\r\nC-1,x,1.00\r\n'
    assert shape(lenient(text).errors) == [(2, "sku", "invalid_sku"), (4, "quantity", "invalid_quantity")]


# --- Rule 8: order ------------------------------------------------------------------------------


def test_rule8_items_and_errors_are_in_file_order():
    text = doc("Z-9,1,1.00", "bad,1,1.00", "A-1,1,1.00", "A-1,x,1", "M-5,2,3.5", "M-5,1,1", "B-2,y,1.00")
    result = lenient(text)
    assert [i.sku for i in result.items] == ["Z-9", "A-1", "M-5"]
    lines = [e.line for e in result.errors]
    assert lines == sorted(lines) == [3, 5, 7, 8]
    assert [e.code for e in result.errors] == ["invalid_sku", "duplicate_sku", "duplicate_sku", "invalid_quantity"]


def test_rule8_ticket_example():
    text = "sku,quantity,unit_price\nA-1,5,19.99\nA-2,x,1.00\nB-1,2,0.29\n\nA-1,9,1.00\n"
    result = lenient(text)
    assert result.items == [Item("A-1", 5, 1999), Item("B-1", 2, 29)]
    assert shape(result.errors) == [(3, "quantity", "invalid_quantity"), (6, "sku", "duplicate_sku")]
    assert strict_error(text).line == 3


# --- Rule 9: strict mode ------------------------------------------------------------------------


def test_rule9_strict_raises_the_first_error_not_the_last():
    error = strict_error(doc("A-1,1,1.00", "B-2,x,1.00", "C-3,1,y", "D-4"))
    assert (error.line, error.column, error.code) == (3, "quantity", "invalid_quantity")


@pytest.mark.parametrize(
    "rows",
    [
        pytest.param(["A-1,1,1.00", "A-1,2,2.00"], id="duplicate"),
        pytest.param(["", "", 'A-1,"1\n2",1.00', "bad"], id="multiline-after-blank-lines"),
        pytest.param(["A-1", "B-2,x,y"], id="field-count-first"),
        pytest.param(["A-1,1,1.005"], id="price"),
    ],
)
def test_rule9_strict_error_equals_first_non_strict_error(rows):
    text = doc(*rows)
    assert strict_error(text) == lenient(text).errors[0]


def test_rule9_strict_stops_at_the_first_rejected_row_even_if_a_later_row_is_valid():
    error = strict_error(doc("A-1,x,1.00", "A-1,1,1.00", "B-2,1,y"))
    assert (error.line, error.code) == (2, "invalid_quantity")


# --- Rule 10: nothing accepted ------------------------------------------------------------------


def test_rule10_all_rows_rejected_gives_empty_items_and_all_errors():
    result = lenient(doc("a,1,1.00", "B-1,x,1.00", "C-1,1,x", "D-1"))
    assert result.items == []
    assert [e.line for e in result.errors] == [2, 3, 4, 5]


def test_rule10_non_strict_does_not_raise_for_row_errors():
    result = lenient(doc("???,???,???"))
    assert isinstance(result, ImportResult)
    assert len(result.errors) == 1
