"""Preview an export schedule without invoking its command."""

from dataclasses import dataclass

_FIELDS = (
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day_of_month", 1, 31),
    ("month", 1, 12),
    ("weekday", 0, 6),
)


class ScheduleError(ValueError):
    def __init__(self, field: str, detail: str) -> None:
        self.field = field
        super().__init__(f"{field}: {detail}")


@dataclass(frozen=True)
class Schedule:
    minute: tuple[int, ...]
    hour: tuple[int, ...]
    day_of_month: tuple[int, ...]
    month: tuple[int, ...]
    weekday: tuple[int, ...]
    command: str


def _expand(text: str, field: str, lower: int, upper: int) -> tuple[int, ...]:
    if text == "*":
        return tuple(range(lower, upper + 1))
    if not text.isascii() or not text.isdecimal():
        raise ScheduleError(field, "preview currently supports only integers and *")
    value = int(text)
    if not lower <= value <= upper:
        raise ScheduleError(field, f"expected {lower}..{upper}")
    return (value,)


def parse_schedule(expression: str) -> Schedule:
    """Split five fields from an opaque command and expand each field."""
    parts = expression.split(maxsplit=5)
    if len(parts) < 5:
        raise ScheduleError(_FIELDS[len(parts)][0], "missing field")
    if len(parts) == 5 or not parts[5].strip():
        raise ScheduleError("command", "missing command")
    minute, hour, day_of_month, month, weekday = [
        _expand(token, field, lower, upper)
        for token, (field, lower, upper) in zip(parts[:5], _FIELDS, strict=True)
    ]
    return Schedule(minute, hour, day_of_month, month, weekday, command=parts[5])


def preview(expression: str) -> str:
    """Format the expanded fields for the operations configuration page."""
    schedule = parse_schedule(expression)
    rows = [
        f"{field}: " + " ".join(str(value) for value in getattr(schedule, field))
        for field, _, _ in _FIELDS
    ]
    return "\n".join([*rows, f"command: {schedule.command}"])
