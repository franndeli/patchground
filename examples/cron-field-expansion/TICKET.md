# Preview scheduled exports

Operations configures a nightly export using a five-field schedule followed by a
command. The preview service currently understands only single numbers and wildcards.
Add list, range and step expansion so the configuration page can explain a schedule
before it is saved. This tool never executes the command or schedules a job.

## Entry point

Implement the missing grammar in `workspace/src/export_schedule.py`.
`parse_schedule(expression: str) -> Schedule` is the public parser.
`Schedule` has immutable tuple attributes `minute`, `hour`, `day_of_month`,
`month`, `weekday` and a string `command`. Keep the existing `preview`
formatter working. Inputs to the parser are strings.

The fields, in order, have these inclusive bounds:

- `minute`: 0–59
- `hour`: 0–23
- `day_of_month`: 1–31
- `month`: 1–12
- `weekday`: 0–6 (there is no Sunday alias 7)

## Required grammar

Each field produces a sorted, duplicate-free tuple of integers.

- `*` selects the full field.
- An unsigned ASCII decimal integer selects one value; leading zeroes are allowed.
- `a-b` selects an inclusive ascending range. Equal endpoints are valid.
- Commas form a union, for example `1,4-6,4` selects `(1, 4, 5, 6)`.
- `*/n` or `a-b/n` selects every nth value starting at that selection's
  lower endpoint. The step must be a positive unsigned ASCII decimal integer.
  A step larger than the range still selects its lower endpoint.
- Commas may combine any of those forms, e.g. `1,4-10/3,*/30`.

Reject out-of-bounds values or endpoints (even if a step would skip an endpoint),
reversed ranges, zero or negative steps, empty union members, a step on a single
integer (`5/2`), extra slashes, malformed tokens, signs and names.
Do not accept whitespace inside a field.

Fields are separated by whitespace, including tabs and newlines. Ignore leading
whitespace. After the fifth field, strip separator whitespace, then preserve the
entire nonempty command remainder verbatim, including its internal and trailing
whitespace. Shell punctuation is just command data.
For example `*/20 9-11 1,15 * 1-5 export --format csv` expands minute to
`(0, 20, 40)`, hour to `(9, 10, 11)`, day-of-month to `(1, 15)`,
and weekday to `(1, 2, 3, 4, 5)`.

Raise `ScheduleError` (a `ValueError`) on invalid input. Its `field` attribute
and message must identify `minute`, `hour`, `day_of_month`, `month`,
`weekday`, or `command`. Missing fields name the first missing positional
field; a missing/whitespace-only command names `command`. Error wording beyond
that name is not fixed.

## Boundaries and checks

Use the standard library. No named months, macros, seconds field, timezone or
calendar calculations, day-of-month/weekday interaction, command execution or
external service. Do not change the documented interfaces or test configuration.
Add focused tests if useful; conventional visible checks are in `checks/visible/tests/`
and appear as `tests/` in a session. Run checks through Patchground's Docker
commands, never directly on the host.

The 60-minute intermediate estimate is provisional, not human-calibrated.
This original Patchground exercise is model-generated, not an employer's interview.
