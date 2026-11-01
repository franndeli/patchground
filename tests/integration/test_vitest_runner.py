"""Actual pinned runtime conformance; authored fixtures execute only through sandbox."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from patchground.runner_assets import VITEST_COMMAND, vitest_assets
from patchground.sandbox import (
    BuildResult,
    Limits,
    RunOutcome,
    TestStatus,
    build_image,
    run_check,
    run_command,
)

pytestmark = pytest.mark.docker
IMPORT = 'import {test, expect, beforeAll, afterAll} from "vitest";\n'
PASS = IMPORT + 'test("works", () => expect(1).toBe(1));\n'


def workspace(root: Path, material: dict[str, str]) -> Path:
    root.mkdir()
    for name, content in material.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return root


@pytest.fixture(scope="module")
def vitest_image(tmp_path_factory: pytest.TempPathFactory) -> BuildResult:
    environment = tmp_path_factory.mktemp("vitest-environment")
    for name, data in vitest_assets().items():
        (environment / name).write_bytes(data)
    return build_image(environment / "Dockerfile", name="vitest-conformance")


def test_locked_toolchain_and_npm_test(vitest_image: BuildResult, tmp_path: Path) -> None:
    ws = workspace(tmp_path / "ws", {})
    checked = run_command(
        vitest_image.image_id, [ws], ["npm", "--prefix", "/opt/patchground", "test"]
    )
    assert checked.exit_code == 0
    version = run_command(
        vitest_image.image_id,
        [ws],
        [
            "node",
            "--input-type=module",
            "-e",
            "import fs from 'node:fs'; console.log(JSON.stringify([process.version, "
            "JSON.parse(fs.readFileSync('/opt/patchground/node_modules/vitest/' + "
            "'package.json')).version, "
            "JSON.parse(fs.readFileSync('/opt/patchground/node_modules/vite/package.json')).version]))",
        ],
    )
    assert version.exit_code == 0
    assert json.loads(version.output_tail) == ["v24.15.0", "5.0.5", "8.3.5"]


def test_identities_runtime_types_and_escaping(vitest_image: BuildResult, tmp_path: Path) -> None:
    name = "literal β & < \" '\n\t name"
    ws = workspace(
        tmp_path / "ws",
        {
            "tests/a.test.ts": IMPORT
            + "enum Value { One = 1 };\n"
            + 'test("same", () => expect(Value.One).toBe(1));\n'
            + f"test({json.dumps(name)}, () => {{ const runtimeOnly: number = 'text'; "
            + "expect(runtimeOnly).toBe('text'); });\n",
            "tests/b.test.ts": IMPORT + 'test("same", () => {});\n',
        },
    )
    result = run_check(vitest_image.image_id, [ws], VITEST_COMMAND)
    assert result.outcome is RunOutcome.PASSED
    assert {case.id for case in result.tests} == {
        "tests/a.test.ts::same",
        f"tests/a.test.ts::{name}",
        "tests/b.test.ts::same",
    }
    assert len(result.tests) == 3
    assert result.log_tail == ""


def test_assertion_failure_preserves_actual_identity(
    vitest_image: BuildResult, tmp_path: Path
) -> None:
    ws = workspace(
        tmp_path / "ws",
        {"tests/example.test.ts": IMPORT + 'test("works", () => expect(1).toBe(2));\n'},
    )
    result = run_check(vitest_image.image_id, [ws], VITEST_COMMAND)
    assert result.outcome is RunOutcome.FAILED
    assert [(case.id, case.status) for case in result.tests] == [
        ("tests/example.test.ts::works", TestStatus.FAILED)
    ]
    assert result.exit_code == 1


def test_skip_todo_and_nested_names(vitest_image: BuildResult, tmp_path: Path) -> None:
    ws = workspace(
        tmp_path / "ws",
        {
            "tests/a.test.ts": PASS
            + 'test.skip("skip", () => {}); test.todo("todo");\n'
            + 'import {describe} from "vitest"; '
            + 'describe("suite", () => { test("nested", () => {}); });'
        },
    )
    result = run_check(vitest_image.image_id, [ws], VITEST_COMMAND)
    assert result.outcome is RunOutcome.PASSED
    assert {case.id: case.status for case in result.tests} == {
        "tests/a.test.ts::works": TestStatus.PASSED,
        "tests/a.test.ts::skip": TestStatus.SKIPPED,
        "tests/a.test.ts::todo": TestStatus.SKIPPED,
        "tests/a.test.ts::suite > nested": TestStatus.PASSED,
    }


@pytest.mark.parametrize(
    "material",
    [
        {},
        {"tests/a.test.ts": IMPORT + 'test("retry", {retry: 1}, () => {});'},
        {"tests/a.test.ts": IMPORT + 'test("repeat", {repeats: 1}, () => {});'},
        {"tests/empty.test.ts": "export const helper = 1;"},
        {"tests/a.test.ts": 'import "./missing.ts";\n' + PASS},
        {"tests/a.test.ts": PASS + 'beforeAll(() => {throw Error("fixture")});\n'},
        {"tests/a.test.ts": PASS + 'afterAll(() => {throw Error("fixture")});\n'},
        {
            "tests/a.test.ts": IMPORT
            + 'test("works", async () => {Promise.reject(Error("fixture"));'
            "await new Promise(resolve => setTimeout(resolve, 30));});"
        },
        {"tests/a.test.ts": IMPORT + 'test("duplicate", () => {}); test("duplicate", () => {});'},
        {"tests/a.test.ts": IMPORT + 'test("bad\\u0000name", () => {});'},
    ],
    ids=[
        "empty",
        "retry",
        "repeat",
        "empty-module",
        "import",
        "before-hook",
        "after-hook",
        "rejection",
        "duplicate",
        "xml",
    ],
)
def test_errors_never_publish_passing_junit(
    vitest_image: BuildResult, tmp_path: Path, material: dict[str, str]
) -> None:
    ws = workspace(tmp_path / "ws", material)
    result = run_check(vitest_image.image_id, [ws], VITEST_COMMAND)
    assert result.outcome is RunOutcome.MISSING_RESULTS
    assert result.tests == ()
    assert result.exit_code == 1


def test_configuration_and_discovery_are_frozen(vitest_image: BuildResult, tmp_path: Path) -> None:
    ws = workspace(
        tmp_path / "ws",
        {
            "tests/a.test.ts": PASS,
            "vitest.config.ts": 'throw Error("must not load");',
            "vite.config.ts": 'throw Error("must not load");',
            "other.spec.ts": 'throw Error("not conventional");',
            "node_modules/ignored.test.ts": 'throw Error("excluded");',
            ".git/ignored.test.ts": 'throw Error("excluded");',
        },
    )
    result = run_check(vitest_image.image_id, [ws], VITEST_COMMAND)
    assert result.outcome is RunOutcome.PASSED
    assert [case.id for case in result.tests] == ["tests/a.test.ts::works"]


def test_exact_file_selection_retains_empty_helpers(
    vitest_image: BuildResult, tmp_path: Path
) -> None:
    ws = workspace(
        tmp_path / "ws",
        {
            "tests/a.test.ts": IMPORT + 'import {value} from "./helper.test.ts";'
            'test("works", () => expect(value).toBe(1));',
            "tests/helper.test.ts": "export const value = 1;",
            "tests/extra-a.test.ts": 'throw Error("not selected by substring");',
        },
    )
    result = run_check(vitest_image.image_id, [ws], VITEST_COMMAND + " --files tests/a.test.ts")
    assert result.outcome is RunOutcome.PASSED
    assert [case.id for case in result.tests] == ["tests/a.test.ts::works"]


@pytest.mark.parametrize(
    "selection",
    [
        "--files",
        "--unknown",
        "--files ../a.test.ts",
        "--files /tests/a.test.ts",
        "--files 'tests/*.test.ts'",
        "--files tests/a.test.ts tests/a.test.ts",
        "--files tests/a.test.ts tests/missing.test.ts",
        "--files .git/a.test.ts",
        "--files node_modules/a.test.ts",
    ],
)
def test_selection_rejects_unsafe_or_missing_files(
    vitest_image: BuildResult, tmp_path: Path, selection: str
) -> None:
    ws = workspace(tmp_path / "ws", {"tests/a.test.ts": PASS})
    result = run_check(vitest_image.image_id, [ws], VITEST_COMMAND + " " + selection)
    assert result.outcome is RunOutcome.MISSING_RESULTS
    assert result.exit_code == 1


def test_all_pass_child_nonzero_withholds_final_junit(
    vitest_image: BuildResult, tmp_path: Path
) -> None:
    # Fault injection in a disposable image, after real collection/execution/close and receipt.
    # Production has no fault-injection flag or alternate exit policy.
    env = tmp_path / "fault-environment"
    env.mkdir()
    harness = vitest_assets()["vitest-runner.mjs"].decode()
    invocation = "await child(process.argv[3], process.argv.slice(4));"
    assert harness.count(invocation) == 1
    harness = harness.replace(invocation, "{ " + invocation + " process.exitCode = 7; }")
    (env / "vitest-runner.mjs").write_text(harness)
    (env / "Dockerfile").write_text(
        f"FROM {vitest_image.image_id}\nCOPY vitest-runner.mjs /opt/patchground/vitest-runner.mjs\n"
    )
    image = build_image(env / "Dockerfile", name="vitest-nonzero-conformance")
    ws = workspace(tmp_path / "ws", {"tests/a.test.ts": PASS})
    proof = run_command(
        image.image_id,
        [ws],
        [
            "sh",
            "-c",
            "node /opt/patchground/vitest-runner.mjs --child /workspace/receipt.json; code=$?; "
            "node --input-type=module -e \"import fs from 'node:fs'; "
            "const r=JSON.parse(fs.readFileSync('/workspace/receipt.json')); "
            'console.log(JSON.stringify([r.trustworthy,r.cases.map(t=>t.state),process.argv[1]]))" '
            '"$code"',
        ],
        limits=Limits(timeout_seconds=60),
    )
    assert proof.exit_code == 0
    assert json.loads(proof.output_tail) == [True, ["passed"], "7"]
    result = run_check(image.image_id, [ws], VITEST_COMMAND)
    assert result.outcome is RunOutcome.MISSING_RESULTS
    assert result.exit_code == 1
    assert result.tests == ()
