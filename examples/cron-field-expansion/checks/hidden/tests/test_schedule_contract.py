import pytest
from export_schedule import ScheduleError, parse_schedule, preview


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("59,0,59 23,0 31,1 12,1 6,0 cmd", ((0, 59), (0, 23), (1, 31), (1, 12), (0, 6))),
        ("1-1/9 4-4/1 31-31/4 12-12/5 6-6/8 cmd", ((1,), (4,), (31,), (12,), (6,))),
        ("*/25 */10 */11 */5 */4 cmd", ((0, 25, 50), (0, 10, 20), (1, 12, 23), (1, 6, 11), (0, 4))),
        (
            "03-09/03 02-08/4 02-09/3 02-11/3 01-06/2 cmd",
            ((3, 6, 9), (2, 6), (2, 5, 8), (2, 5, 8, 11), (1, 3, 5)),
        ),
        ("*,1-3,2 */100 1,1,2 1-12/20 0-6/99 cmd", (tuple(range(60)), (0,), (1, 2), (1,), (0,))),
    ],
)
def test_all_field_expansions(expression, expected):
    result = parse_schedule(expression)
    assert (
        tuple(
            getattr(result, name) for name in ("minute", "hour", "day_of_month", "month", "weekday")
        )
        == expected
    )


@pytest.mark.parametrize(
    ("position", "token", "field"),
    [
        (0, "0-60/99", "minute"),
        (1, "0-24/99", "hour"),
        (2, "0-1", "day_of_month"),
        (2, "1-32/99", "day_of_month"),
        (3, "0", "month"),
        (3, "1-13", "month"),
        (4, "0-7/100", "weekday"),
        (0, ",1", "minute"),
        (0, "1,", "minute"),
        (0, ",", "minute"),
        (1, "*/", "hour"),
        (1, "*/-2", "hour"),
        (1, "*/+2", "hour"),
        (2, "1-4/0", "day_of_month"),
        (2, "1-4/", "day_of_month"),
        (3, "1-4/2/3", "month"),
        (3, "1-2-3", "month"),
        (4, "6-1", "weekday"),
        (4, "*/1.5", "weekday"),
        (0, "+1", "minute"),
        (0, "1.0", "minute"),
        (0, "\u0661", "minute"),
        (0, "1e1", "minute"),
        (0, "*/²", "minute"),
        (1, "1/1", "hour"),
        (2, "?", "day_of_month"),
        (3, "JAN", "month"),
        (4, "MON", "weekday"),
    ],
)
def test_rejects_malformed_members_without_losing_field_identity(position, token, field):
    parts = ["0", "0", "1", "1", "0"]
    parts[position] = token
    with pytest.raises(ScheduleError) as error:
        parse_schedule(" ".join([*parts, "export"]))
    assert error.value.field == field
    assert field in str(error.value)


@pytest.mark.parametrize(
    ("expression", "missing"),
    [
        (" \n\t ", "minute"),
        ("0", "hour"),
        ("0 0", "day_of_month"),
        ("0 0 1", "month"),
        ("0 0 1 1", "weekday"),
        ("0 0 1 1 0", "command"),
        ("0 0 1 1 0\n\t ", "command"),
    ],
)
def test_missing_input_reports_the_first_missing_position(expression, missing):
    with pytest.raises(ScheduleError) as error:
        parse_schedule(expression)
    assert error.value.field == missing
    assert missing in str(error.value)


def test_multiline_command_and_extra_numeric_words_are_opaque():
    result = parse_schedule("\n0\t0\n1 1\t0\n \t09 export\t--x  a\nb  ")
    assert result.command == "09 export\t--x  a\nb  "
    assert preview("0-4/2 0 1 1 0 echo  x").splitlines()[0] == "minute: 0 2 4"
    assert parse_schedule("1 2 3 4 5 $(not-a-program) > nowhere").command == (
        "$(not-a-program) > nowhere"
    )


def test_repeated_parses_do_not_accumulate_previous_fields():
    first = parse_schedule("1,9,3 0 1 1 0 cmd")
    second = parse_schedule("*/59 0 1 1 0 cmd")
    assert first.minute == (1, 3, 9)
    assert second.minute == (0, 59)
