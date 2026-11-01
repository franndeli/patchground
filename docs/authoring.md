# Author a first challenge

Install the CLI from this checkout with `uv tool install .`. Python 3.12+, Git and a running
Docker engine are needed for validation and practice; `pgnd new` itself does not need Docker.

## Start from a working contract

In an empty authoring directory:

```sh
pgnd new my-challenge
pgnd validate my-challenge
```

The ID must contain lowercase letters/digits separated by single hyphens and must match its folder.
Python/debug remains the default. Choose `--type debug|feature` and `--lang python|typescript`
for any of the four starters, for example `pgnd new my-feature --type feature --lang typescript`.
An existing
destination, including an empty directory or symlink, is refused. Choose another ID; there is no
force flag. Every command supports `--json`.

The generated example is intentionally tiny and broken, with visible baseline checks, hidden
regressions and a reference patch. It should validate unchanged. `new` only creates files: it does
not initialize Git, build an image or run authored code.

## Replace the starter as a unit

- `challenge.yaml`: public metadata, environment and check locations; keep the ID/folder aligned.
- `TICKET.md`: realistic symptoms, required behavior, constraints and a clear public entry point.
  Do not disclose the fix or require unstated behavior.
- `workspace/`: the broken application and configuration learners receive. No reference solution
  or hidden checks belong here.
- `checks/visible/`: checks learners receive and can extend.
- `checks/hidden/`: independent verification of the ticket's requirements. Keep hidden sources out
  of learner materials and public command output.
- `solution/reference.patch`: a minimal application fix relative to `workspace/`, not a replacement
  for tests. Do not make it pass by modifying tests.
- `environment/Dockerfile`: install pinned dependencies at build time. Run-phase networking is
  internal only; do not depend on downloads or external services during checks.

Do not execute challenge code or tests on the host. Use `pgnd validate` and session `pgnd check`.
For the supported tampering probes, use conventional pytest `test_*.py` / `*_test.py` modules with
static test functions/methods. TypeScript starters use a pinned Vitest container toolchain;
keep the generated environment resources together and the test command unchanged. Use `.test.ts`
files with named `test`/`expect` imports from `vitest`, standalone literal unique test names and
callbacks. Suites, hooks, aliases, modifiers, dynamic registration and changed harness/helper inputs
may make additional evidence unsupported. Runtime checks do not prove TypeScript type correctness.
Inspect every validation gate: `not_run` is not a pass.

Set honest authorship, licensing and provenance when replacing the starter. Model metadata that
cannot be established must say so; do not attribute generated work to an unobserved model.
For generated material, put this in `challenge.yaml` (replace the example with observed facts):

```yaml
provenance: generated
generated_by:
  model: "unknown (configured agent default)"
  prompt_version: my-authoring-v1
```

A statement in the ticket alone does not set the manifest provenance fields.

## Validate and try it

```sh
pgnd validate my-challenge
pgnd show my-challenge
pgnd start my-challenge
```

Open the printed workspace in your editor; run `pgnd check` there before and after making a fix.
Use a separate clean session to test the ticket without relying on the reference. The source folder
remains an authoring artifact; work on the session workspace while solving.

Validation builds once and uses twelve check containers for the supported starter: broken/reference,
bounded determinism and editable-test tampering. It writes ignored local `verification.json`
evidence; that is not portable CI proof. Use `--no-write` to leave records untouched.

Ask an independent person to author and solve from these docs. Automated generated-template tests
prove mechanics, not challenge realism, difficulty or human usability.

## Failure recovery

Fix environment issues reported by `pgnd doctor` before validating. If creation fails during writes,
Patchground removes only entries it created whose identity still matches; concurrent additions or
replacements survive and can leave a partial destination. Inspect it manually before choosing a new
ID. Do not run multiple writers against an authoring folder.

## Share committed challenges

See [Pinned challenge packs](packs.md) for installation, complete execution-consent reviews,
updates and removal. Pack operations do not publish a repository or grant official trust.
