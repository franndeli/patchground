"""Regression-test evidence: do the learner's new or changed tests fail before and pass after?

The probe supports direct ``pytest`` commands and the canonical frozen Vitest runner, using
static conventional test definitions. Candidates are exactly the test definitions
that are new or changed between the captured original and final trees. They are selected alone
twice inside the sandbox with identical test material and a fixed runner configuration: once
against the original code and once against the final code. Anything the probe cannot reason about
is reported as ``not_established`` rather than guessed, and nothing here ever runs on the host.

Evidence carries test identities and statuses only, never raw runner output.
"""

from __future__ import annotations

import ast
import filecmp
import os
import re
import shlex
import shutil
import stat
import tempfile
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from patchground import sandbox as engine
from patchground.runner_assets import VITEST_COMMAND
from patchground.sandbox import RunOutcome, RunResult, TestResult, TestStatus
from patchground.sessions.models import CheckTest
from patchground.verify import vitest_adapter
from patchground.verify.pytest_adapter import (
    TestNode,
    UnsupportedPytest,
    is_test_filename,
    split_pytest_command,
    test_definitions,
)
from patchground.verify.runners import (
    VITEST_EXCLUDED_PARTS,
    is_vitest_path,
    runner_for,
    vitest_identity,
)

Status = Literal["verified", "not_verified", "not_established"]

MAX_CANDIDATES = 200
MAX_TEXT_BYTES = 1024 * 1024  # runner configuration files
JUNIT_TARGET = "--junitxml=$PG_RESULTS/junit.xml"
JUNIT_VALUES = ("$PG_RESULTS/junit.xml", "${PG_RESULTS}/junit.xml")
SKIPPED_PARTS = frozenset({".git", "__pycache__", ".pytest_cache"})
RUNNER_CONFIG = frozenset(
    {"pytest.ini", ".pytest.ini", "pytest.toml", ".pytest.toml", "tox.ini", "setup.cfg"}
    | {"pyproject.toml", "conftest.py"}
)
HARNESS_PARTS = frozenset({"tests", "test", "testing"})
SAFE_PATH = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]*")
# Settings and hooks that change what pytest collects, selects or skips.
CONFIG_CONTROLS = re.compile(
    r"^\s*(python_files|python_classes|python_functions|norecursedirs|addopts|"
    r"confcutdir|consider_namespace_packages)\b",
    re.MULTILINE,
)
CONFTEST_CONTROLS = re.compile(
    r"\b(collect_ignore(_glob)?|pytest_(ignore_collect|collect_file|collection\w*|"
    r"pycollect\w*|generate_tests|configure|runtest\w*|deselected))\b"
)
COLLECTION_OPTIONS = frozenset(
    {"-k", "-m", "-x", "-c", "--deselect", "--ignore", "--ignore-glob", "--lf", "--ff", "--nf"}
    | {"--sw", "--co", "--collect-only", "--maxfail", "--exitfirst", "--pyargs", "--rootdir"}
    | {"--confcutdir", "--import-mode", "--last-failed", "--failed-first", "--new-first"}
    | {"--stepwise", "--override-ini", "-o", "--junitxml", "--junit-xml"}
)
SIMPLE_OPTIONS = re.compile(
    r"-[qvsl]+|-r[A-Za-z]+|--(quiet|verbose|no-header|no-summary|disable-warnings|"
    r"strict-markers|strict-config|showlocals)|--color=(yes|no|auto)|"
    r"--tb=(auto|long|short|line|native|no)|--durations=\d+"
)


class RegressionSandbox(Protocol):
    """The one sandbox operation regression evidence needs (injectable for tests)."""

    def run_check(self, image_id: str, layers: Sequence[Path], command: str) -> RunResult: ...


class RegressionEvidence(BaseModel):
    """Factual regression-test outcome; never a score or a submission gate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Status
    reason: str
    candidates: tuple[str, ...] = ()
    verified_tests: tuple[str, ...] = ()
    before_tests: tuple[CheckTest, ...] = ()
    after_tests: tuple[CheckTest, ...] = ()
    before_outcome: str | None = None
    after_outcome: str | None = None


class _Unsupported(Exception):
    """The probe cannot establish evidence; the message becomes the reason."""


@dataclass(frozen=True)
class _Candidate:
    module: str  # relative POSIX path of the test module
    qualname: str  # Python qualified name or exact Vitest literal name
    exact_identity: bool = False

    @property
    def id(self) -> str:
        """The runner-specific JUnit identity, preserving literal Vitest names."""
        if self.exact_identity:
            return vitest_identity(self.module, self.qualname)
        *classes, name = self.qualname.split("::")
        dotted = ".".join([self.module.removesuffix(".py").replace("/", "."), *classes])
        return f"{dotted}::{name}"

    @property
    def node_id(self) -> str:
        return f"{self.module}::{self.qualname}"


def evaluate_regression(
    original: Path,
    final: Path,
    image_id: str,
    command: str,
    *,
    sandbox: RegressionSandbox = engine,
) -> RegressionEvidence:
    """Probe whether the final tests fail on the original code and pass on the final code.

    ``original`` and ``final`` are captured private trees, never the live workspace. Unsupported
    inputs return ``not_established``. Engine and storage faults raise
    :class:`patchground.sandbox.SandboxError` (or ``OSError``) so the caller can retry.
    """
    try:
        plan = _plan(Path(original), Path(final), command)
    except _Unsupported as exc:
        return RegressionEvidence(status="not_established", reason=str(exc))
    if not plan.candidates:
        return RegressionEvidence(
            status="not_verified", reason="no new or changed test definitions were found"
        )
    ids = tuple(c.id for c in plan.candidates)
    with tempfile.TemporaryDirectory(prefix="patchground-regression-") as scratch:
        before_tree, after_tree = Path(scratch, "original"), Path(scratch, "final")
        _copy(plan.original_files, before_tree)
        _copy(plan.final_files, after_tree)
        for module in plan.test_modules:
            if plan.exact_identities and module not in plan.final_files:
                (before_tree / module).unlink()
                continue
            material = plan.final_files[module]
            _copy_file(material, before_tree / module)
            if plan.exact_identities:
                _copy_file(material, after_tree / module)
                names = {c.qualname for c in plan.candidates if c.module == module}
                for tree in (before_tree, after_tree):
                    vitest_adapter.select_tests(tree / module, names)
        before = sandbox.run_check(image_id, [before_tree], plan.command)
        before_tests = _sanitized(before.tests)
        stop = _judge_before(before, ids, exact=plan.exact_identities)
        if stop is not None:
            return RegressionEvidence(
                status=stop[0],
                reason=stop[1],
                candidates=ids,
                before_tests=before_tests,
                before_outcome=before.outcome.value,
            )
        after = sandbox.run_check(image_id, [after_tree], plan.command)
    after_tests = _sanitized(after.tests)
    outcomes = {"before_outcome": before.outcome.value, "after_outcome": after.outcome.value}
    stop = _judge_after(after, ids, exact=plan.exact_identities)
    if stop is None:
        stop = _same_identities(before, after)
    verified = _verified(before, after)
    if stop is None and not verified:
        stop = ("not_verified", "no selected test failed on the original and passed on the final")
    status: Status = stop[0] if stop else "verified"
    return RegressionEvidence(
        status=status,
        reason=stop[1]
        if stop
        else "selected tests fail on the original code and pass on the final",
        candidates=ids,
        verified_tests=() if stop else verified,
        before_tests=before_tests,
        after_tests=after_tests,
        **outcomes,
    )


# -------------------------------------------------------------------------------------- planning


@dataclass(frozen=True)
class _Plan:
    candidates: tuple[_Candidate, ...]
    test_modules: tuple[str, ...]
    original_files: dict[str, Path]
    final_files: dict[str, Path]
    command: str
    exact_identities: bool = False


def _plan(original: Path, final: Path, command: str) -> _Plan:
    split = split_pytest_command(command)
    if split is None:
        if runner_for(command) == "vitest":
            return _vitest_plan(original, final, command)
        raise _Unsupported("the test command is not a supported frozen runner invocation")
    invocation, arguments = split
    options, scope = _runner_options(arguments)
    original_files, final_files = _files(original), _files(final)
    changed = {
        rel
        for rel in original_files.keys() | final_files.keys()
        if rel not in original_files
        or rel not in final_files
        or not filecmp.cmp(original_files[rel], final_files[rel], shallow=False)
    }
    modules, candidates = _candidates(original_files, final_files, changed)
    if candidates:
        _reject_unreliable(original_files, final_files, changed, candidates)
        if len(candidates) > MAX_CANDIDATES:
            raise _Unsupported("too many new or changed tests to select safely")
        _check_scope(candidates, scope)
        command = _selected_command(invocation, options, candidates)
    return _Plan(tuple(candidates), tuple(modules), original_files, final_files, command)


def _vitest_plan(original: Path, final: Path, command: str) -> _Plan:
    original_files = _files(original, excluded=VITEST_EXCLUDED_PARTS)
    final_files = _files(final, excluded=VITEST_EXCLUDED_PARTS)
    changed = {
        rel
        for rel in original_files.keys() | final_files.keys()
        if rel not in original_files
        or rel not in final_files
        or not filecmp.cmp(original_files[rel], final_files[rel], shallow=False)
    }
    parsed: list[dict[str, vitest_adapter.TestModule]] = []
    try:
        for files in (original_files, final_files):
            parsed.append(
                {
                    rel: vitest_adapter.parse_module(path)
                    for rel, path in files.items()
                    if is_vitest_path(PurePosixPath(rel))
                }
            )
    except vitest_adapter.UnsupportedVitest as exc:
        raise _Unsupported(f"a TypeScript test module cannot be analysed: {exc}") from exc
    before, after = parsed
    candidates: list[_Candidate] = []
    for rel, module in sorted(after.items()):
        previous = before.get(rel)
        for name, definition in module.definitions.items():
            old = previous.definitions.get(name) if previous is not None else None
            if old is not None and old.fingerprint == definition.fingerprint:
                continue
            candidate = _Candidate(rel, name, exact_identity=True)
            try:
                vitest_identity(rel, name)
            except ValueError as exc:
                raise _Unsupported("a TypeScript test identity cannot be selected safely") from exc
            candidates.append(candidate)
    if len(candidates) > MAX_CANDIDATES:
        raise _Unsupported("too many new or changed tests to select safely")
    if candidates:
        for rel in before.keys() & after.keys():
            if before[rel].helper_fingerprint != after[rel].helper_fingerprint:
                raise _Unsupported("TypeScript test imports or helpers changed")
        homes = {rel.rpartition("/")[0] for rel in before.keys() | after.keys()}
        for rel in changed:
            name = rel.rsplit("/", 1)[-1]
            if _vitest_harness_file(name):
                raise _Unsupported("TypeScript runner, dependency or configuration files changed")
            if (rel in before and before[rel].definitions) or (
                rel in after and after[rel].definitions
            ):
                continue
            directory = rel.rpartition("/")[0]
            near = any(
                directory == home or (home and directory.startswith(home + "/")) for home in homes
            )
            if near or HARNESS_PARTS & set(directory.split("/")):
                raise _Unsupported("helper or harness files near the tests changed")
    if candidates:
        selected_modules = sorted({c.module for c in candidates})
        command = f"{VITEST_COMMAND} --files {shlex.join(selected_modules)}"
    return _Plan(
        tuple(candidates),
        tuple(sorted(before.keys() | after.keys())),
        original_files,
        final_files,
        command,
        exact_identities=True,
    )


def _vitest_harness_file(name: str) -> bool:
    return name in {
        "package.json",
        "package-lock.json",
        "npm-shrinkwrap.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "bun.lock",
        "bun.lockb",
        "pnpm-workspace.yaml",
        ".npmrc",
        ".yarnrc",
        ".yarnrc.yml",
        ".node-version",
        ".nvmrc",
        "Dockerfile",
        "vitest-runner.mjs",
    } or name.startswith(("vitest.config.", "vite.config.", "tsconfig.", "Dockerfile."))


def _runner_options(arguments: list[str]) -> tuple[list[str], list[str]]:
    """Split the frozen pytest arguments into preserved options and positional test paths."""
    options: list[str] = []
    scope: list[str] = []
    junit = False
    index = 0
    while index < len(arguments):
        word = arguments[index]
        index += 1
        name = word.split("=", 1)[0]
        if name in ("--junitxml", "--junit-xml"):
            value = word.partition("=")[2]
            if "=" not in word and index < len(arguments):
                value, index = arguments[index], index + 1
            if value not in JUNIT_VALUES:
                raise _Unsupported("the JUnit target must be $PG_RESULTS/junit.xml")
            junit = True
        elif word == "-p" or word.startswith("-p"):
            plugin = arguments[index] if word == "-p" and index < len(arguments) else word[2:]
            index += word == "-p"
            if plugin != "no:cacheprovider":
                raise _Unsupported("only -p no:cacheprovider is supported")
            options += ["-p", plugin]
        elif word.startswith("-"):
            if name in COLLECTION_OPTIONS or not SIMPLE_OPTIONS.fullmatch(word):
                kind = "collection control" if name in COLLECTION_OPTIONS else "runner option"
                raise _Unsupported(f"{kind} {_shown(name)} is not supported")
            options.append(word)
        elif "::" in word:
            raise _Unsupported("test selection by node id in the test command is not supported")
        else:
            scope.append(_normalized(word))
    if not junit:
        raise _Unsupported("the test command must write --junitxml=$PG_RESULTS/junit.xml")
    return options, scope


def _shown(text: str) -> str:
    return repr("".join(c for c in text if c.isprintable())[:40])


def _normalized(path: str) -> str:
    parts = [part for part in path.split("/") if part not in ("", ".")]
    if path.startswith("/") or ".." in parts:
        raise _Unsupported("test paths outside the workspace are not supported")
    return "/".join(parts)


def _files(root: Path, *, excluded: frozenset[str] = frozenset()) -> dict[str, Path]:
    """Map relative POSIX path -> ordinary file; anything unusual makes the tree unsupported."""
    if not root.is_dir() or root.is_symlink():
        raise _Unsupported("a captured tree is missing or not a directory")
    files: dict[str, Path] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        base = Path(dirpath)
        kept = []
        for name in sorted(dirnames):
            if name in SKIPPED_PARTS or name in excluded:
                continue
            if (base / name).is_symlink():
                raise _Unsupported("a captured tree contains a symbolic link")
            kept.append(name)
        dirnames[:] = kept
        for name in filenames:
            path = base / name
            mode = path.lstat().st_mode
            if name.endswith(".pyc"):
                continue
            if not stat.S_ISREG(mode):
                raise _Unsupported("a captured tree contains a link or special file")
            files[path.relative_to(root).as_posix()] = path
    return files


def _definitions(path: Path) -> dict[str, TestNode]:
    try:
        return test_definitions(path)
    except UnsupportedPytest as exc:
        raise _Unsupported(f"a test module cannot be analysed: {exc}") from exc


def _candidates(
    original: dict[str, Path], final: dict[str, Path], changed: set[str]
) -> tuple[list[str], list[_Candidate]]:
    """Changed static test modules and the test definitions that are new or changed in them."""
    modules: list[str] = []
    candidates: list[_Candidate] = []
    for rel in sorted(changed & final.keys()):
        if not rel.endswith(".py") or not is_test_filename(rel.rsplit("/", 1)[-1]):
            continue
        after = _definitions(final[rel])
        if not after:
            continue  # helper-only module with a test-like name; handled as harness
        modules.append(rel)
        before = _definitions(original[rel]) if rel in original else {}
        for qualname, node in after.items():
            old = before.get(qualname)
            if old is None or ast.dump(old) != ast.dump(node):
                if not SAFE_PATH.fullmatch(rel) or any(p.startswith("-") for p in rel.split("/")):
                    raise _Unsupported("a test path cannot be selected safely")
                candidates.append(_Candidate(rel, qualname))
    return modules, candidates


def _reject_unreliable(
    original: dict[str, Path],
    final: dict[str, Path],
    changed: set[str],
    candidates: Sequence[_Candidate],
) -> None:
    """Refuse when runner configuration, collection controls or test harness files differ."""
    for rel in sorted(changed):
        if rel.rsplit("/", 1)[-1] in RUNNER_CONFIG:
            raise _Unsupported("pytest configuration, pyproject or conftest files changed")
    for files in (original, final):
        for rel, path in files.items():
            name = rel.rsplit("/", 1)[-1]
            if name not in RUNNER_CONFIG:
                continue
            if path.stat().st_size > MAX_TEXT_BYTES:
                raise _Unsupported("a runner configuration file is too large to analyse")
            text = path.read_text(encoding="utf-8", errors="replace")
            pattern = CONFTEST_CONTROLS if name == "conftest.py" else CONFIG_CONTROLS
            if pattern.search(text):
                raise _Unsupported("collection controls in pytest configuration or conftest")
    homes = {c.module.rpartition("/")[0] for c in candidates}
    for rel in sorted(changed):
        if _is_test_file(final, original, rel):
            continue
        directory = rel.rpartition("/")[0]
        near = any(
            directory == home or (home != "" and directory.startswith(home + "/")) for home in homes
        )
        if near or HARNESS_PARTS & set(directory.split("/")):
            raise _Unsupported("helper or harness files near the tests changed")


def _is_test_file(final: dict[str, Path], original: dict[str, Path], rel: str) -> bool:
    """A changed conventional module with static tests (compared test material, not harness)."""
    path = final.get(rel)
    if path is None:
        return rel in original and rel.endswith(".py") and _static_test_module(original[rel])
    return rel.endswith(".py") and _static_test_module(path)


def _static_test_module(path: Path) -> bool:
    name = path.name
    return is_test_filename(name) and bool(_definitions(path))


def _check_scope(candidates: Sequence[_Candidate], scope: Sequence[str]) -> None:
    for candidate in candidates:
        if scope and not any(
            part == "" or candidate.module == part or candidate.module.startswith(part + "/")
            for part in scope
        ):
            raise _Unsupported("a selected test is outside the paths in the test command")


def _selected_command(
    invocation: list[str], options: list[str], candidates: Sequence[_Candidate]
) -> str:
    fixed = shlex.join([*invocation, *options, "--rootdir=."])
    return f"{fixed} {JUNIT_TARGET} {shlex.join(c.node_id for c in candidates)}"


# ------------------------------------------------------------------------------------- copying


def _copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)
    shutil.copy2(source, target)
    # Captures are read-only; only these private disposable copies may be mutated.
    target.chmod(stat.S_IMODE(target.stat().st_mode) | stat.S_IWUSR)


def _copy(files: dict[str, Path], target: Path) -> None:
    target.mkdir()
    for rel, path in files.items():
        _copy_file(path, target / rel)


# ------------------------------------------------------------------------------------- judging


def _sanitized(tests: Sequence[TestResult]) -> tuple[CheckTest, ...]:
    return tuple(
        CheckTest(id="".join(c for c in t.id if c.isprintable())[:240], status=t.status)
        for t in tests
    )


Verdict = tuple[Status, str] | None


def _base(test: TestResult) -> str:
    return f"{test.classname}::{test.name.split('[', 1)[0]}"


def _inconclusive(label: str, run: RunResult) -> Verdict:
    if run.outcome in (RunOutcome.MISSING_RESULTS, RunOutcome.LIMIT_EXCEEDED):
        return "not_established", f"the {label} run was inconclusive ({run.outcome.value})"
    return None


def _collected(label: str, run: RunResult, ids: Sequence[str], *, exact: bool = False) -> Verdict:
    if any(len(test.id) > 240 or not test.id.isprintable() for test in run.tests):
        return "not_established", "test identities cannot be reported safely without alteration"
    if exact and Counter(t.id for t in run.tests) != Counter(ids):
        return "not_verified", f"selected tests were not collected exactly on the {label} code"
    seen = {t.id if exact else _base(t) for t in run.tests}
    if not set(ids) <= seen or not seen <= set(ids):
        return (
            "not_verified",
            f"selected tests were not collected exactly on the {label} code",
        )
    return None


def _judge_before(run: RunResult, ids: Sequence[str], *, exact: bool = False) -> Verdict:
    stop = _inconclusive("original", run) or _collected("original", run, ids, exact=exact)
    if stop is not None:
        return stop
    if any(t.status not in (TestStatus.PASSED, TestStatus.FAILED) for t in run.tests):
        return "not_verified", "original run has errored or skipped tests"
    if all(t.status == TestStatus.PASSED for t in run.tests):
        return "not_verified", "selected tests already pass on the original code"
    if run.outcome != RunOutcome.FAILED:
        return "not_verified", "the original runner did not complete as a test failure"
    return None


def _judge_after(run: RunResult, ids: Sequence[str], *, exact: bool = False) -> Verdict:
    stop = _inconclusive("final", run) or _collected("final", run, ids, exact=exact)
    if stop is not None:
        return stop
    if any(t.status != TestStatus.PASSED for t in run.tests):
        return "not_verified", "a selected test does not pass on the final code"
    if run.outcome != RunOutcome.PASSED:
        return "not_verified", "the final runner did not complete successfully"
    return None


def _statuses(run: RunResult) -> dict[str, list[TestStatus]]:
    grouped: dict[str, list[TestStatus]] = {}
    for test in run.tests:
        grouped.setdefault(test.id, []).append(test.status)
    return grouped


def _same_identities(before: RunResult, after: RunResult) -> Verdict:
    counts = Counter(t.id for t in before.tests)
    if counts != Counter(t.id for t in after.tests):
        return "not_verified", "selected test identities differ between original and final runs"
    return None


def _verified(before: RunResult, after: RunResult) -> tuple[str, ...]:
    after_statuses = _statuses(after)
    return tuple(
        test_id
        for test_id, statuses in _statuses(before).items()
        if all(s == TestStatus.FAILED for s in statuses)
        and after_statuses.get(test_id, []) == [TestStatus.PASSED] * len(statuses)
    )
