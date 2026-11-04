import pytest
from export_schedule import ScheduleError, parse_schedule


@pytest.mark.parametrize(
    ("minute", "expected"),
    [
        ("0" * 4400, (0,)),
        ("0" * 4400 + "59", (59,)),
        ("*/" + "1" + "0" * 4400, (0,)),
        ("3-8/" + "9" * 4500, (3,)),
        ("0" * 4400 + "5-" + "0" * 4400 + "9/2", (5, 7, 9)),
        ("*/" + "0" * 4400 + "20", (0, 20, 40)),
    ],
    ids=[
        "long-zero-literal",
        "padded-literal",
        "huge-wildcard-step",
        "huge-range-step",
        "padded-range",
        "padded-step",
    ],
)
def test_long_numerals_follow_the_same_grammar(minute, expected):
    assert parse_schedule(f"{minute} 0 1 1 0 export").minute == expected


@pytest.mark.parametrize(
    "minute",
    ["9" * 4500, "0-" + "9" * 4500, "*/" + "0" * 4500, "*/" + "9" * 4500 + "x"],
    ids=["huge-value", "huge-endpoint", "long-zero-step", "long-invalid-step"],
)
def test_invalid_long_numerals_keep_field_specific_errors(minute):
    with pytest.raises(ScheduleError, match="minute") as error:
        parse_schedule(f"{minute} 0 1 1 0 export")
    assert error.value.field == "minute"
