# Validate challenges with the GitHub Action

The repository root is a reusable composite Action versioned with the CLI. It runs the same
`pgnd validate` verifier in Docker on a Linux runner; there is no second verifier, hosted
execution or publishing step. The Action installs Patchground from its own pinned source with
locked core dependencies (no AI extra). Installation clears inherited Python import/startup
variables and runs from the trusted Action directory, with a private runner-temp environment.
Validation uses `python -I`, preventing checkout code and inherited `PYTHONPATH` from being imported.
Temporary storage must be outside the selected checkout; unsafe nesting is refused before installation.

## Example workflow

Pin both the checkout and this Action to full commit SHAs that you have reviewed. Replace the
placeholders; `<owner>/<repo>` is where this Action lives.

```yaml
name: validate-challenges
on:
  pull_request:

permissions:
  contents: read

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<full-commit-sha>
        with:
          fetch-depth: 0
          persist-credentials: false
      - id: patchground
        uses: <owner>/<repo>@<full-commit-sha>
        with:
          challenge-directory: challenges
          allow-execution: "true"
      - if: always()
        uses: actions/upload-artifact@<full-commit-sha>
        with:
          name: validation-report
          path: ${{ steps.patchground.outputs.report-file }}
```

## Inputs and output

| Input | Default | Meaning |
| --- | --- | --- |
| `source-directory` | `github.workspace` | Git checkout read by commit; relative paths resolve from the job workspace. Never modified. |
| `challenge-directory` | `.` | One directory inside the checkout: a challenge, a pack root, or a folder whose immediate children are challenges. |
| `base-commit` | empty | Commit to compare with. Empty uses the pull request base or push `before` SHA when present. |
| `allow-execution` | `"false"` | Must be exactly `"true"` to build and run challenge Dockerfiles and checks. |

Output `report-file` is the path of one aggregate JSON report. The path is set just before the
verifier starts, and the file is created exclusively (never overwriting) in a private directory
outside the checkout, so a validation failure (exit 1 or 2) still leaves a report to upload; use
`if: always()` on later steps. It is **not** guaranteed on every failure: if setup or dependency
installation fails, or the report location is unsafe or the runner's storage fails, the output may
be unset or the file absent or empty. A cancelled run records a short cancellation error where it
can. Guard uploads accordingly (for example `if-no-files-found: ignore`).

## What is validated

Validation reads the **committed** content of the checkout, not dirty or generated working-tree
files. With a usable base, changed and new challenges are validated; a pack metadata change
revalidates all. Removed challenges are reported and never executed. If nothing changed the run
succeeds with an explicit *skipped* result: this does not claim unchanged challenges were tested.

Without a usable base, the Action validates **every** discovered challenge; it never silently skips.
Use `fetch-depth: 0` (or at least enough history to contain the base) so the base commit exists. In
a shallow checkout that lacks it, the run falls back to all challenges, which is slower but safe.

The report lists selected, unchanged and removed challenges and the verifier's factual outcomes.
Checks that cannot run keep the existing `not_run` meaning; it is not a pass. Reports contain no
hidden source, raw logs, credentials or absolute scratch paths.

Exit status: `0` success or skip; `1` a challenge failed validation or a manifest is invalid;
An empty/invalid challenge selection also exits `1`. `2` means usage, infrastructure or missing
execution consent; cancellation exits `130`. A missing
`allow-execution: "true"` refuses before any build.

## Running untrusted contributions

Validation builds and runs Dockerfiles and tests from the contribution. Treat them as untrusted:

- Use the `pull_request` trigger, not `pull_request_target`. Fork pull requests then run with a
  read-only token and no secrets. Keep `permissions: contents: read`.
- Require maintainer approval for fork workflows (repository Settings, Actions, "Require approval
  for all outside collaborators") and read the Dockerfiles and checks before approving a run.
- Do not expose repository, organization or environment secrets to the job, and do not set
  `persist-credentials` on checkout.
- The build phase may use the network; the run phase uses an internal network only.
- Passing validation is verification of the committed challenge, not approval to publish it.

The Action sets no consent beyond the single run and persists no blanket grant. It performs no
deployment, publishing, registry or account operations.
