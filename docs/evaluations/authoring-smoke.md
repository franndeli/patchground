# Authoring acceptance smoke — first public-product wave

## Scope and setup

Synthetic author A1 used a fresh installed wheel with no AI extras, a scratch folder, the public
authoring guide, installed CLI help and generated starter files. The coordinator supplied the
installation; this was not an independent installation or human-author trial.

Agent: Codex, configured default. Exact model identity was not established. The worker received no
implementation-team context or curated exercise solutions. Its instruction-only source restriction
was not a filesystem sandbox: the worker was launched from the development workspace but assigned
all authoring work to scratch. No claim of adversarial isolation is made.

The tested wheel came from the first authoring/content wave based on `e32befa` plus that wave's
then-uncommitted changes, version 0.0.1. It was not a published package.

## Observed outcomes

- Created the unmodified Python/debug starter through `pgnd new`; all six validation gates passed.
- Adapted it into a string-joining exercise with a coherent ticket, application, checks and reference.
- Authored broken application: three visible checks passed and four hidden checks failed.
- Reference application: all seven checks passed.
- Determinism and editable-test tampering passed; no gate reported `not_run`.
- Two validation invocations, both through Docker. No host execution of challenge code.
- No coordinator authoring help was requested; no product edits, new purchases or publication.
- The author reported that provenance needed a manifest example. The guide now includes one and
  explains that ticket text alone does not set manifest provenance. That documentation revision has
  not been independently retried.

Coordinator separately verified a clean wheel installation with no AI extras through
`new → validate → show → start → check → fix → check → reset → check`. All six gates passed,
the broken/fixed/reset outcomes matched expectations, and workspace Git state remained unchanged.
The first smoke setup used a symlinked temporary-path alias and was correctly rejected by session
path safety; using its canonical path resolved that environment setup issue.

## Limits

One small synthetic authoring attempt is evidence for mechanics, not realism, difficulty, human
usability or community demand. It is not one of the ten synthetic learner attempts. Independent
human onboarding and authoring acceptance remain pending.

Raw local records contain runtime/session details and are not published. No hidden/reference
sources or provider credentials are included here.
