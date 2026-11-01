# Public-product delivery brief

## Owner request

Expand Patchground from its playable local prototype toward a complete public product, with a
public presence at **patchground.dev**. Deliver the roadmap through coordinated, supervised agents
where useful. Maintain durable records so context resets do not lose direction or evidence.

Use a cohort of ten synthetic learners spanning available model capability levels to exercise the
product. These are agent evaluations, not ten human interviews or proof of human usability.

## Verified starting point

- `583ad23`: local discovery, safe reset, environment diagnostics and onboarding.
- `5860fa6`: three-run deterministic validation.
- `e32befa`: bounded editable pytest test-tampering validation.
- Last recorded local full-suite result: 516 tests passed with Docker required; lint, formatting,
  types and spec validation passed. Git safety hooks passed on publication.
- CI and secret scanning succeeded for all three commits, including a fresh observation for
  `e32befa` during programme setup.
- The independent fresh-human-user acceptance trial has not been performed.

## Delivery and evidence rules

- Preserve the local-first core, Docker execution isolation, user Git state, privacy, optional AI,
  and test-backed outcomes without overall scores unless an owning contract is explicitly revised.
- The existing current-slice exclusions must be reconciled before implementing newly authorized
  subsystems. Broad ambitions do not silently override safety rules or product non-goals.
- Use bounded milestones with explicit acceptance criteria, reviewed integration and reproducible
  verification. Record actual completion separately from launches, queued jobs and predictions.
- Keep active progress in the shared TODO plan; keep durable decisions in owning specs. Maintain
  milestone handoffs with commits, exact checks, blockers and the next action.
- Synthetic learner trials use fresh isolated workspaces without reference solutions; record model,
  configuration, assistance and observable outcomes. Distinguish solver failures from product
  failures. Do not claim that synthetic feedback establishes human demand or usability.
- Do not log credentials, private prompts containing secrets, personal paths or machine identifiers.

## Approved delivery boundaries

- **Local-first public product:** CLI plus public documentation/challenge catalog at patchground.dev;
  no accounts or hosted challenge execution. AI remains optional and bring-your-own-provider.
- **Existing access only:** use already configured subscriptions and local models. No purchased
  credits, new paid services or unbounded metered API spending. Report unavailable model diversity
  or exhausted access rather than substituting new spending.
- **Approval at publication:** build and verify deployable artifacts, but ask before DNS changes,
  production deployment, package publication or release creation. Existing Git pushes remain
  authorized. Hosting/provider selection and access are still open.

## Available execution and launch prerequisites

Read-only inventory found Pi, Codex, Claude Code and Ollama installed. Codex reports ChatGPT
subscription authentication; Claude Code reports an authenticated claude.ai account. Ollama lists
`ornith-1.5:9b` locally. No credentials were printed or copied, and no inference was purchased.
These are launch candidates, not proof that every model alias or tool-use mode works; each selected
learner configuration needs a supervised smoke trial before inclusion in the cohort.

GitHub CLI, uv and Docker are installed. Existing Git pushes and CI workflows already operate.
Hosting provider, DNS control, package-publisher identity and release permissions are not yet
established. Inventory does not authorize any production, DNS, package or release operation.

## Roadmap to reconcile into milestones

- Authoring scaffold and independently authored challenges.
- More realistic challenges and learner-facing session completion / verified outcomes.
- Remaining practice commands and safe internal history.
- Pack distribution, trust/consent, author contribution workflow and validation integration.
- Documentation and a public presence at patchground.dev.
- Optional AI debrief and generation experiments, with explicit usefulness/quality gates. The owner
  subsequently deferred AI debrief from launch after the local experiment did not establish reliable
  interview quality; see [the evaluation](evaluations/ai-debrief-smoke.md). The owner also explicitly
  deferred the generator experiment to prioritize learner trials and core-product hardening.
- Broader language/runner support and other expansion only with defined scope and acceptance.
- Mixed-model synthetic trials, remediation, and separate real-human validation.

The owner approved the delivery boundaries above. Individual feature designs, hosting selection
and public launch actions still follow the repository's design and publication gates.
