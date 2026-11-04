# Export schedule preview

The application module is `src/export_schedule.py`; its `parse_schedule`
function supplies a `Schedule` to the operations page's `preview` formatter.
The current parser already handles wildcard and literal fields. Extend the grammar
as described in the session ticket; do not turn this into a scheduler.

Visible tests arrive under `tests/` in your session. Use `pgnd check` there.
No command in a schedule is ever executed.
