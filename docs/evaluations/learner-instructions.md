# Shared synthetic learner instructions

The coordinator supplies the attempt ID, declared challenge timebox, installed CLI executable,
assigned workspace and public ticket. Those substitutions are the only per-attempt changes to these
instructions. No reference solution, hidden source or implementation-team discussion is supplied.

## Task

Solve the supplied ticket in your assigned workspace using your normal editing tools. Read the
application and visible checks, investigate the behavior, make a focused change and add an appropriate
regression test when relevant. You may inspect the installed CLI's public help.

Use the supplied executable as `PGND` below; run it from your assigned workspace:

- `PGND status --json`: inspect the session and timer.
- `PGND check --json`: run verification in Docker. Exit 1 means checks failed, not necessarily an
  infrastructure fault. Read the structured outcome.
- `PGND hint --json`: request a hint if useful; disclose every hint used.
- `PGND run --json -- <command> <arguments>`: optional diagnostic execution in a disposable container.
- `PGND submit --json`: finalize once ready; this freezes test-backed outcomes and a debrief.
- `PGND report --json`: reread the saved factual debrief without running verification again.

The coordinator started the fresh session before handoff. This cohort does not evaluate independent
installation or challenge discovery. The installed candidate is built from the registered commit,
not the implementation checkout's working tree.

## Boundaries

- Stop at the supplied challenge timebox or 20 `check` invocations, whichever occurs first. Include
  investigation, editing and command time. Do not reset the timer or extend the budget. If the budget
  expires, stop work and report the last available outcome; do not run extra commands to improve it.
- Challenge/application/test commands run only through Patchground's container commands. Never run
  Python application code, pytest, Node, npm, Vitest or authored scripts directly on the host.
  Host tools may read and edit your assigned files and invoke the installed CLI.
- Stay inside the assigned workspace. Do not inspect its parent `.session` metadata, hidden checks,
  original snapshots, reference solutions, other attempts, the implementation checkout or installed
  package implementation. Do not search the web or other repositories for solutions.
- Do not inspect or copy credentials, change agent authentication, install models, purchase inference,
  delegate to other agents or alter Docker/CLI enforcement. Existing client authentication is managed
  by the client, not by files you create.
- Do not commit, stage, change branches, reset Git or otherwise modify Git metadata. This restriction
  lets the coordinator measure whether normal CLI operations preserve the initial learner Git state.
- Do not modify files after submission. Do not create extra coordinator-report files in the workspace.
- If infrastructure blocks progress, use the injected Orca question/escalation mechanism. Do not repair
  the product or infer success. Assistance and environmental recovery will be recorded, not concealed.

## Completion

Follow the injected Orca preamble to send exactly one `worker_done`, then idle. Use `succeeded` only
when submitted checks passed; otherwise use `failed` and state the stop reason. Either outcome is a
valid evaluation record, not permission for an automatic replacement attempt.

Report relative files changed, check/hint counts, final check and regression outcomes if available,
any assistance, blockers or reference exposure, and your model ID only if explicitly available from
runtime metadata. Otherwise say unknown. Do not include personal paths, credentials, hidden sources
or raw private traces. The coordinator independently checks the saved report and command events.
