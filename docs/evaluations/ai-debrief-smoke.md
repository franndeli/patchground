# Deferred AI debrief experiment

## Disposition

The owner explicitly deferred AI coaching from launch after bounded local evaluation failed to
establish reliable interview quality. The implementation is preserved privately for follow-up, not
included in the package or CLI. The factual `submit` / `report` workflow is unchanged. No AI SDK
was added to the launch dependency set.

## Configuration and observations

The existing local Ollama `ornith-1.5:9b` model was used with temperature 0.1, a 32,768-token context
setting, a 2,048-token output budget and a 120-second transport deadline. No model was downloaded,
no cloud inference was performed and no inference was purchased. Anthropic transport had fixture
coverage only.

Each full attempt used a fresh Python starter session with actual Docker checks, a submitted fix
and a verified before-fail/after-pass regression. Answers were scripted by the implementation
coordinator, not supplied by independent learners. These attempts do not count toward the ten-learner
cohort or independent-human acceptance.

Five full attempts were run as the implementation evolved:

1. Default model reasoning: one question, then an uncertain transport failure; two calls, 190.25
   seconds including session setup. No automatic transport retry occurred.
2. Reasoning disabled: exhausted three response-validation attempts without an accepted question;
   97.47 seconds. A separate one-call diagnostic identified a premature final response at zero
   answers, despite schema-valid fields; its deliberately imposed call cap ended that diagnostic.
3. Phase-specific decoding schemas: completed after three answers and five calls, including one
   repaired final response; 76.41 seconds. Questions included duplication and a placeholder. Some
   citations pointed to diff headers rather than supporting the claim. Completion was not usefulness.
4. Duplicate/placeholder rejection: two accepted questions, then exhausted validation retries;
   six calls, 55.6 seconds.
5. Minimum question length aligned with decoding: one accepted, longer placeholder, then exhausted
   validation retries; four calls, 29.51 seconds. Length did not establish substantive quality.

The final experimental version therefore has **no successful full live interview**. All original
failures remain recorded; an earlier completion is not presented as final-version acceptance.
Citation existence establishes traceability only, not semantic truth. Further tuning stopped rather
than repeatedly sampling until a favorable result appeared.

## Verification and limits

- Latest experimental AI/CLI unit check: 161 passed. An earlier scoped run including the real
  submitted-session Docker integration passed 162 tests; no final full experimental suite or
  experimental clean-wheel acceptance was completed.
- Every full live attempt preserved immutable submission bytes, saved factual reports, session audit
  events and learner Git bytes. Reading the saved result did not make another model call.
- After removing the experiment, `PATCHGROUND_REQUIRE_DOCKER=1 uv run --quiet pytest -q --tb=short`
  passed **1,104 tests**. Ruff check passed; format check covered 171 files; mypy passed 68 source files.
- The restored core wheel builds without AI coaching modules or an Anthropic dependency; CLI help
  excludes the deferred `debrief` command.
- Independent-human usefulness and coaching acceptance remain unestablished. Revival requires a
  renewed design/quality review, complete verification and honest model-specific evidence.
