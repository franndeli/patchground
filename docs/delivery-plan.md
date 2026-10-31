# Public-product delivery plan

This is a delivery ledger, not a claim that planned capabilities exist. Durable product decisions
live in `goal-and-requirements.md`, `architecture.md` and owning contracts/SPECs. Approved programme
boundaries and earlier verified commits live in [the launch brief](launch-brief.md).

## Completion definition

Prepare a coherent local-first product: installable CLI, documented authoring/distribution, curated
practice content, test-backed session outcomes, public documentation/catalog artifacts, and a
reproducible synthetic evaluation report. No hosted challenge execution, accounts or overall score.

Public launch is a separate approval gate. Human usefulness, market demand and optional AI quality
cannot be declared proven by automated or synthetic tests. The historical roadmap's conditional
ideas receive explicit dispositions; they are not silently treated as mandatory implemented features.

## Milestones

### A. Authoring and content

- Ship `pgnd new` with packaged resources, safe non-overwriting creation, human/JSON results, and a
  documented clean-install authoring path. Approved first template: runnable Python/debug.
- Add two realistic challenges, reaching three curated exercises. Validate each in Docker, prove
  broken/reference outcomes, and test repeatability and supported tampering resistance.
- Give an independently launched author worker only the public authoring instructions and verify
  its output. Label this synthetic authoring evidence, not the independent-human author trial.

### B. Session completion and verified outcomes

- Implement submit/report with frozen final evidence and explicit missing-evidence states.
- Verify regression tests against pristine and final code; distinguish failed reproduction,
  unsupported conventions and infrastructure faults from a verified regression test.
- Add hints, container commands, session browsing and safe internal history without changing user
  Git HEAD/branches/index/staging. Resolve lifecycle/compatibility decisions before implementing.

### C. Distribution and contribution

- Pinned Git packs, unambiguous resolution and explicit consent before untrusted build/run.
- Author/contributor documentation and reusable validation automation without bypassing scans.
- Agree launch language/type coverage, then add needed adapters and representative content.
  Multi-container services and progressive stages require separate contracts; do not imply support.

### D. Public site and optional experiments

- Build documentation/catalog artifacts for patchground.dev. Review a concrete UI proposal before
  implementing it; choose hosting with the owner before production changes.
- Implement optional evidence-grounded AI coaching only behind explicit context preview/consent,
  safe provider configuration and core-without-AI tests.
- Evaluate a bounded generator on supported repositories; retain experimental labeling unless
  validation and useful-content review support promotion. No inference purchases or hidden costs.

### E. Evaluation and hardening

- Run ten isolated synthetic learner attempts across the available model capability tiers. Record
  exact model/configuration, task, time/command budget, help provided and observable outcomes.
- Do not provide reference solutions or implementation-team context to learner workers. Document
  the actual access boundary; prompt restrictions are not an adversarial sandbox.
- Distinguish product defects, solver failures, environment failures and inconclusive trials.
  Fix product defects and rerun affected cases without rewriting original trial outcomes.
- Keep real-human onboarding/authoring trials as separately pending acceptance gates.

### F. Release preparation and publication

- Verify a clean install, core without AI, local offline checks after image build, JSON/error
  contracts, Git safety, documentation links/build, secrets scans and the full Docker suite.
- Prepare versioned artifacts, changelog, migration/compatibility notes and reproducible checks.
- Request explicit approval for DNS, production deployment, package publication and releases.
  An artifact ready to deploy is not a deployed product; a pushed commit is not passing CI.

## Resume protocol

1. Read AGENTS.md, the launch brief, this ledger and the live TODO plan.
2. Check Git status and current commits; never overwrite unfinished work or assume remote CI.
3. Read the current milestone's owning specs and accepted task-spec before editing.
4. Recover any active Orca Run/Task/Dispatch from its recorded receipt; do not duplicate workers.
5. Continue the first open step. Record decisions, exact checks, integration commits, blockers and
   the next action at meaningful checkpoints; keep credentials and personal paths out of records.
6. At context transitions, preserve active handles and local artifact locations in a local resume
   note rather than publishing runtime-specific machine identifiers.

## Current checkpoint

- Product/budget/publication boundaries approved and recorded in the launch brief.
- Published baseline: bounded anti-gaming validation (`e32befa`); CI and secret scan succeeded.
- First authoring/content wave implemented locally: `new`, packaged runnable starter and three
  curated examples. Full Docker-required suite: 543 passed; lint, format, types and graph passed.
- Clean installed wheel (no AI extras): new/validate/show/start/check/fix/reset succeeded, all six
  validation gates passed, and workspace Git state stayed unchanged.
- Existing Codex/Claude subscriptions and a local model are available; individual configurations
  still require smoke tests. The approved cohort protocol is in `docs/synthetic-evaluation.md`.
- Both independent challenge implementation workers settled. No synthetic learner trials yet.
- Independent synthetic author A1 created and adapted a starter from public instructions; both
  validations passed all six gates without authoring help. Evidence/limits are recorded in
  `docs/evaluations/authoring-smoke.md`; this is not a human trial or a learner-cohort attempt.
- Next: commit/push this verified wave and agree the submit/report/regression-test design. Human
  trials remain pending.
