import pytest
from export_schedule import ScheduleError, parse_schedule


@pytest.mark.parametrize(
    ("field", "expression", "expected"),
    [
        ("hour", "0 " + "0" * 6200 + "23 1 1 0 cmd", (23,)),
        ("day_of_month", "0 0 " + "0" * 5100 + "31 1 0 cmd", (31,)),
        ("month", "0 0 1 */" + "7" * 6000 + " 0 cmd", (1,)),
        ("weekday", "0 0 1 1 2-6/" + "1" * 4700 + " cmd", (2,)),
        ("hour", "0 */" + "0" * 5000 + "7 1 1 0 cmd", (0, 7, 14, 21)),
        ("month", "0 0 1 " + "0" * 4900 + "2-" + "0" * 4900 + "8/3 0 cmd", (2, 5, 8)),
        ("minute", "*/" + "0" * 5100 + "8" * 5000 + ",59,0 0 1 1 0 cmd", (0, 59)),
    ],
    ids=[
        "hour-padding",
        "day-padding",
        "month-huge-step",
        "weekday-huge-step",
        "hour-padded-step",
        "month-padded-range",
        "huge-step-union",
    ],
)
def test_unbounded_decimal_spellings_preserve_numeric_meaning(field, expression, expected):
    assert getattr(parse_schedule(expression), field) == expected


@pytest.mark.parametrize(
    ("field", "expression"),
    [
        ("hour", "0 " + "0" * 5000 + "24 1 1 0 cmd"),
        ("day_of_month", "0 0 " + "9" * 6000 + " 1 0 cmd"),
        ("month", "0 0 1 1-" + "9" * 5500 + " 0 cmd"),
        ("weekday", "0 0 1 1 " + "9" * 6000 + "-6 cmd"),
        ("month", "0 0 1 */" + "0" * 5200 + " 0 cmd"),
        ("hour", "0 */" + "5" * 5100 + "x 1 1 0 cmd"),
        ("weekday", "0 0 1 1 */" + "0" * 5100 + "\u0661 cmd"),
        ("day_of_month", "0 0 1-" + "0" * 5500 + " 1 0 cmd"),
    ],
    ids=[
        "padded-out-of-range",
        "huge-literal",
        "huge-upper-endpoint",
        "huge-lower-endpoint",
        "all-zero-step",
        "bad-suffix",
        "non-ascii-suffix",
        "padded-reversed-range",
    ],
)
def test_invalid_long_numbers_always_identify_the_field(field, expression):
    with pytest.raises(ScheduleError) as error:
        parse_schedule(expression)
    assert error.value.field == field
    assert field in str(error.value)
