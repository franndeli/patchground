"""Vitest planning uses inert syntax; container results are supplied by a fake sandbox."""

from collections.abc import Sequence
from pathlib import Path

import pytest

from patchground.report.regression import RegressionEvidence, evaluate_regression
from patchground.sandbox import RunOutcome, RunResult, TestResult, TestStatus

COMMAND = "node /opt/patchground/vitest-runner.mjs"
IMPORTS = "import {test, expect} from 'vitest';\nimport {value} from '../src/app';\n"
OLD = "test('old failure',()=>{expect(value).toBe(0)});\n"
NEW = "test('new [literal]',()=>{expect(value).toBe(2)});\n"
IDENTITY = "tests/app.test.ts::new [literal]"
ORIGINAL = {"src/app.ts": "export const value=1;", "tests/app.test.ts": IMPORTS + OLD}
FINAL = {"src/app.ts": "export const value=2;", "tests/app.test.ts": IMPORTS + OLD + NEW}
FAIL, PASS = TestStatus.FAILED, TestStatus.PASSED


def run(*tests: tuple[str, TestStatus], outcome: RunOutcome | None = None) -> RunResult:
    results = tuple(
        TestResult(identity, identity.partition("::")[2], identity.partition("::")[0], status)
        for identity, status in tests
    )
    if outcome is None:
        outcome = RunOutcome.FAILED if any(t.status == FAIL for t in results) else RunOutcome.PASSED
    return RunResult(outcome, results, 0, None, "PRIVATE raw runner log")


class FakeSandbox:
    def __init__(self, runs: tuple[RunResult, ...]) -> None:
        self.runs = list(runs)
        self.calls: list[tuple[dict[str, str], str]] = []

    def run_check(self, image_id: str, layers: Sequence[Path], command: str) -> RunResult:
        assert image_id == "sha256:image"
        (tree,) = layers
        files = {
            p.relative_to(tree).as_posix(): p.read_text() for p in tree.rglob("*") if p.is_file()
        }
        self.calls.append((files, command))
        return self.runs.pop(0)


def evaluate(
    tmp_path: Path,
    *runs: RunResult,
    original: dict[str, str] | None = None,
    final: dict[str, str] | None = None,
    command: str = COMMAND,
) -> tuple[RegressionEvidence, FakeSandbox]:
    trees = [tmp_path / "original", tmp_path / "final"]
    for root, files in zip(
        trees,
        (ORIGINAL if original is None else original, FINAL if final is None else final),
        strict=True,
    ):
        root.mkdir(parents=True)
        for rel, text in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    for root in trees:
        for path in root.rglob("*"):
            if path.is_file():
                path.chmod(0o444)
    box = FakeSandbox(runs)
    evidence = evaluate_regression(*trees, "sha256:image", command, sandbox=box)
    return evidence, box


def test_real_added_test_uses_identical_selected_material_and_exact_bracket_name(
    tmp_path: Path,
) -> None:
    evidence, box = evaluate(tmp_path, run((IDENTITY, FAIL)), run((IDENTITY, PASS)))
    assert evidence.status == "verified"
    assert evidence.candidates == evidence.verified_tests == (IDENTITY,)
    (before, before_command), (after, after_command) = box.calls
    assert before_command == after_command == COMMAND + " --files tests/app.test.ts"
    assert before["tests/app.test.ts"] == after["tests/app.test.ts"] == IMPORTS + "\n" + NEW
    assert before["src/app.ts"] == ORIGINAL["src/app.ts"]
    assert after["src/app.ts"] == FINAL["src/app.ts"]
    assert "PRIVATE" not in evidence.model_dump_json()
    assert (tmp_path / "original/tests/app.test.ts").read_text() == IMPORTS + OLD
    assert (tmp_path / "final/tests/app.test.ts").read_text() == IMPORTS + OLD + NEW


@pytest.mark.parametrize("phase", ["before", "after"])
@pytest.mark.parametrize(
    "kind",
    [
        "missing",
        "extra",
        "duplicate",
        "skip",
        "error",
        "bracket",
        "loader",
        "missing_results",
        "limit",
    ],
)
def test_ambiguous_or_unsuccessful_results_do_not_verify(
    tmp_path: Path, phase: str, kind: str
) -> None:
    status = FAIL if phase == "before" else PASS
    bad = {
        "missing": run(),
        "extra": run((IDENTITY, status), ("tests/app.test.ts::old failure", status)),
        "duplicate": run((IDENTITY, status), (IDENTITY, status)),
        "skip": run((IDENTITY, TestStatus.SKIPPED)),
        "error": run((IDENTITY, TestStatus.ERRORED)),
        "bracket": run((IDENTITY + "[extra]", status)),
        "loader": run((IDENTITY, status), outcome=RunOutcome.ERRORED),
        "missing_results": run(outcome=RunOutcome.MISSING_RESULTS),
        "limit": run(outcome=RunOutcome.LIMIT_EXCEEDED),
    }[kind]
    runs = (bad,) if phase == "before" else (run((IDENTITY, FAIL)), bad)
    evidence, _ = evaluate(tmp_path, *runs)
    expected = "not_established" if kind in {"missing_results", "limit"} else "not_verified"
    assert evidence.status == expected
    assert not evidence.verified_tests


def test_already_passing_and_unrelated_failure_do_not_verify(tmp_path: Path) -> None:
    evidence, box = evaluate(tmp_path, run((IDENTITY, PASS)))
    assert evidence.status == "not_verified" and len(box.calls) == 1
    evidence, _ = evaluate(tmp_path / "unrelated", run(("tests/app.test.ts::old failure", FAIL)))
    assert evidence.status == "not_verified"


@pytest.mark.parametrize(
    "rel",
    [
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "vitest.config.ts",
        "vite.config.ts",
        "tsconfig.json",
        ".npmrc",
        "Dockerfile",
        "vitest-runner.mjs",
        "tests/helper.ts",
        "tests/data/cases.json",
        "tests/helper.test.ts",
    ],
)
def test_changed_harness_and_nearby_helpers_are_unsupported(tmp_path: Path, rel: str) -> None:
    content = "export const helper=1;" if rel.endswith(".ts") else "{}"
    evidence, box = evaluate(tmp_path, final=FINAL | {rel: content})
    assert evidence.status == "not_established"
    assert not box.calls


@pytest.mark.parametrize("helper", ["const helper=1;", "import helper from './helper';"])
def test_changed_existing_module_helpers_and_imports_are_unsupported(
    tmp_path: Path, helper: str
) -> None:
    evidence, box = evaluate(
        tmp_path, final=FINAL | {"tests/app.test.ts": IMPORTS + helper + OLD + NEW}
    )
    assert evidence.status == "not_established" and not box.calls


@pytest.mark.parametrize(
    "bad",
    [
        "test(name,()=>{});",
        "test.skip('x',()=>{});",
        "const thing: = 1;",
        "test('x',()=>{});test('x',()=>{});",
    ],
)
def test_all_conventional_modules_are_parsed_even_unchanged(tmp_path: Path, bad: str) -> None:
    extra = {"elsewhere/other.test.ts": "import {test} from 'vitest';" + bad}
    evidence, box = evaluate(tmp_path, original=ORIGINAL | extra, final=FINAL | extra)
    assert evidence.status == "not_established" and not box.calls
    assert bad not in evidence.reason


def test_deleted_modules_are_absent_and_final_helpers_are_preserved(
    tmp_path: Path,
) -> None:
    removed = "import {test} from 'vitest';export const deletedHelper=1;test('gone',()=>{});"
    unchanged = "import {test} from 'vitest';const helper=2;test('keep old',()=>{});"
    helper = "export const fixture=3;"
    evidence, box = evaluate(
        tmp_path,
        run((IDENTITY, FAIL)),
        run((IDENTITY, PASS)),
        original=ORIGINAL
        | {
            "tests/gone.test.ts": removed,
            "tests/unchanged.test.ts": unchanged,
            "tests/helper.test.ts": helper,
        },
        final=FINAL | {"tests/unchanged.test.ts": unchanged, "tests/helper.test.ts": helper},
    )
    assert evidence.status == "verified"
    for files, _ in box.calls:
        assert "tests/gone.test.ts" not in files
        assert all("deletedHelper" not in source for source in files.values())
        assert files["tests/unchanged.test.ts"] == "import {test} from 'vitest';const helper=2;"
        assert files["tests/helper.test.ts"] == helper


def test_no_candidates_and_formatting_only_are_not_verified(tmp_path: Path) -> None:
    for index, final in enumerate(
        (
            ORIGINAL,
            {"src/app.ts": "export const value=2;"},
            ORIGINAL | {"tests/app.test.ts": IMPORTS + "// trivia\n" + OLD},
        )
    ):
        evidence, box = evaluate(tmp_path / str(index), final=final)
        assert evidence.status == "not_verified" and not box.calls


def test_changed_definition_is_selected(tmp_path: Path) -> None:
    name = "tests/app.test.ts::old failure"
    evidence, box = evaluate(
        tmp_path,
        run((name, FAIL)),
        run((name, PASS)),
        final=FINAL | {"tests/app.test.ts": IMPORTS + OLD.replace("Be(0)", "Be(2)")},
    )
    assert evidence.status == "verified" and evidence.candidates == (name,)
    assert box.calls[0][0]["tests/app.test.ts"] == box.calls[1][0]["tests/app.test.ts"]


def test_source_and_candidate_bounds(tmp_path: Path) -> None:
    for index, source in enumerate(
        (" " * (1024 * 1024 + 1), IMPORTS + "".join(f"test('n{i}',()=>{{}});" for i in range(201)))
    ):
        evidence, box = evaluate(tmp_path / str(index), final=FINAL | {"tests/app.test.ts": source})
        assert evidence.status == "not_established" and not box.calls


@pytest.mark.parametrize(
    "rel", ["tests/space name.test.ts", "tests/-bad.test.ts", "tests/" + "x" * 220 + ".test.ts"]
)
def test_unsafe_or_truncated_paths_are_unsupported(tmp_path: Path, rel: str) -> None:
    evidence, box = evaluate(tmp_path, final=FINAL | {rel: IMPORTS + NEW})
    assert evidence.status == "not_established" and not box.calls


@pytest.mark.parametrize("command", [COMMAND + " --watch", "npm test", COMMAND + " ; true"])
def test_only_canonical_recipe_supported(tmp_path: Path, command: str) -> None:
    evidence, box = evaluate(tmp_path, command=command)
    assert evidence.status == "not_established" and not box.calls


def test_frozen_discovery_excludes_node_modules(tmp_path: Path) -> None:
    ignored = {"node_modules/dependency/bad.test.ts": "test(dynamic, callback);"}
    evidence, box = evaluate(
        tmp_path,
        run((IDENTITY, FAIL)),
        run((IDENTITY, PASS)),
        original=ORIGINAL | ignored,
        final=FINAL | ignored,
    )
    assert evidence.status == "verified"
    assert all(not any("node_modules" in rel for rel in files) for files, _ in box.calls)


def test_deleted_helper_only_module_is_ambiguous(tmp_path: Path) -> None:
    evidence, box = evaluate(
        tmp_path,
        original=ORIGINAL | {"tests/helper.test.ts": "export const deletedHelper=1;"},
    )
    assert evidence.status == "not_established"
    assert not box.calls
