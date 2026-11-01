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
- AI coaching is explicitly deferred from launch after the local experiment failed to establish
  reliable interview quality. Preserve the implementation privately for follow-up; retain the
  consent/privacy and core-without-AI requirements for any revival. See
  [the evaluation and disposition](evaluations/ai-debrief-smoke.md).
- The owner also deferred the generator experiment from launch to prioritize learner trials and
  hardening. No generator evaluation or generator command is claimed. Existing authoring tools and
  the six curated challenges remain the launch content scope.

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
- Published authoring/content wave: `323804b`; CI and secret scanning succeeded.
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
- Submit/report design approved and implemented locally: immutable bundles, retryable pre-commit
  faults, exact interrupted-audit recovery, failed-attempt submission and conservative pytest
  regression evidence. Structural test changes are facts, never strength grades. Final local gates:
  667 Docker-required tests passed, plus lint/format/types/spec validation. A clean wheel without AI
  extras passed failed submission/readback and before-fails/after-passes regression submission,
  preserving workspace Git state.
- Published submit/report wave: `bc42ec9`; its CI and secret scanning both succeeded.
- Practice tools verified: hints, disposable diagnostic commands, local session browsing and private
  checkpoint history. All applicable ignore sources are honored or capture is unavailable; unsafe
  executable selection cannot run workspace-supplied Git. Empty Docker volumes retain non-root write
  ownership. Final gates: 773 Docker-required tests, lint/format, strict types (54 source files), and
  a clean wheel without AI extras passed. Wheel evidence covered hints/run/history, immutable failed
  submission/readback, no command-output persistence and unchanged workspace Git bytes.
- Periodic capture and snapshot restoration are explicitly deferred. Ignore includes, linked
  worktrees and other unsupported contexts leave optional history unavailable, never weaken filtering.
- Practice wave published as `b9dde79`.
- Pinned packs verified locally: public HTTPS/local committed sources, immutable commit/content
  identity, installed discovery and complete explicit consent before execution or changed activation.
  Cache paths cannot bypass consent; removal preserves frozen sessions. Hardened publication retains
  referenced content after post-commit durability failures and reports partial cleanup honestly.
- Pack gates: 862 Docker-required tests, lint/format (145 files), types (62 source files), valid spec
  graph and a clean wheel without AI extras. Wheel checks covered consent, installed validation with
  no cache writes, and check/submit/report after removal with unchanged workspace Git bytes. HTTPS
  transport policy is hermetically tested; the end-to-end wheel source was a real local Git repository.
- A final rerun exposed an existing Docker stdout/stderr ordering assumption. The test now requires
  both exact lines without inventing cross-stream chronology; container behavior is unchanged.
- Portability follow-up `77db755` passed remote CI and secret scanning. Linux pack staging identity
  races were reproduced and fixed; the intermittent OOM symptom remains unreproduced after 112 probes,
  with conservative production classification unchanged. See `evaluations/ci-portability.md`.
- Contribution automation is implemented in this repository: explicit execution consent, committed
  changed/all selection, safe JSON, no-change skip and unchanged source/Git. Local gates: 928
  Docker-required tests, lint/format, types and clean-wheel/Action-shell smoke without AI passed.
  Integration caught and fixed original-source Git selection, installer Python import exposure and
  root-challenge folder identity. See `evaluations/automation-smoke.md` for evidence and limits.
- Runner/catalog expansion implemented: six challenges across Python/TypeScript and debug/feature,
  four packaged starters, a pinned Vitest harness and inert Tree-sitter evidence adapter. TypeScript
  tests establish runtime behavior only. Local acceptance: 1,104 Docker-required tests, lint/format,
  types, schema and clean core-wheel starter/submission smoke passed. Integration found and fixed
  private-mode runner resource permissions and read-only snapshot probe copies. See
  `evaluations/coverage-smoke.md`; remote acceptance remains pending until observed.
- The owner deferred AI coaching from launch after five bounded local-model attempts. The final
  experimental version did not complete a live interview; an earlier completion had poor questions.
  Implementation and integration patches are privately preserved, with no AI code or SDK added to
  the launch build. The restored core passed 1,104 Docker-required tests, Ruff/format and mypy.
  See `evaluations/ai-debrief-smoke.md`; synthetic operator answers are not learner or human trials.
- The owner also deferred the generator experiment; it has not been evaluated or implemented.
- Next: separate-owner site handoff and core-product evaluation. Human trials and the ten-learner cohort remain pending; no deployment, package
  publication or release is implied.
