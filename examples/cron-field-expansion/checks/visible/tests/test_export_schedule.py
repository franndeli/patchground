import pytest
from export_schedule import ScheduleError, parse_schedule, preview


def test_existing_literal_and_wildcard_preview():
    schedule = parse_schedule("5 9 1 * 0 export")
    assert schedule.minute == (5,)
    assert schedule.month == tuple(range(1, 13))
    assert schedule.command == "export"
    assert preview("5 9 1 2 0 export").splitlines() == [
        "minute: 5",
        "hour: 9",
        "day_of_month: 1",
        "month: 2",
        "weekday: 0",
        "command: export",
    ]


def test_export_preview_combines_ranges_and_unions():
    schedule = parse_schedule("*/20 9-11 1,15 * 1-5 export --format csv")
    assert schedule.minute == (0, 20, 40)
    assert schedule.hour == (9, 10, 11)
    assert schedule.day_of_month == (1, 15)
    assert schedule.weekday == (1, 2, 3, 4, 5)


def test_steps_are_anchored_and_unions_are_sorted_unique():
    schedule = parse_schedule("1,4-10/3,*/30 8-12/3 1 1 0 export")
    assert schedule.minute == (0, 1, 4, 7, 10, 30)
    assert schedule.hour == (8, 11)


def test_command_is_preserved_as_data():
    schedule = parse_schedule(" \t05\t9 1 2 0 \t export  --name 'daily x'; echo nope  ")
    assert schedule.minute == (5,)
    assert schedule.command == "export  --name 'daily x'; echo nope  "


@pytest.mark.parametrize(
    "token",
    [
        "60",
        "8-2",
        "*/0",
        "1,,2",
        "5/2",
        "*/2/3",
        "-1",
        "JAN",
    ],
)
def test_invalid_minute_forms_name_the_field(token):
    with pytest.raises(ScheduleError, match="minute") as error:
        parse_schedule(f"{token} 0 1 1 0 export")
    assert error.value.field == "minute"


@pytest.mark.parametrize(
    ("expression", "field"),
    [
        ("", "minute"),
        ("0 1", "day_of_month"),
        ("0 1 2 3", "weekday"),
        ("0 1 2 3 4   ", "command"),
        ("0 24 1 1 0 export", "hour"),
        ("0 0 0 1 0 export", "day_of_month"),
        ("0 0 1 13 0 export", "month"),
        ("0 0 1 1 7 export", "weekday"),
    ],
)
def test_missing_parts_and_other_field_bounds(expression, field):
    with pytest.raises(ScheduleError, match=field) as error:
        parse_schedule(expression)
    assert error.value.field == field
