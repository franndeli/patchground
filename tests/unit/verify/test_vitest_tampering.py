from collections import Counter
from pathlib import Path

import pytest

from patchground.runner_assets import VITEST_COMMAND
from patchground.verify.runners import runner_for, vitest_identity
from patchground.verify.tampering import UnsupportedTampering, mutate, vitest_identities
from patchground.verify.tampering import test_modules as find_modules

SOURCE = 'import {test, expect} from "vitest";\ntest("works", () => {expect(1).toBe(1)});\n'


def test_runner_recipe_is_exact() -> None:
    assert runner_for(VITEST_COMMAND) == "vitest"
    assert runner_for("pytest -q") == "pytest"
    for command in (
        VITEST_COMMAND + " && true",
        "npm test",
        VITEST_COMMAND + " --files a.test.ts",
        'unterminated \\"',
    ):
        assert runner_for(command) is None


def test_module_selection_preserves_helpers_and_excluded_trees(tmp_path: Path) -> None:
    test = tmp_path / "a.test.ts"
    test.write_text(SOURCE)
    helper = tmp_path / "helpers.test.ts"
    helper.write_text("export const fixture = 1;")
    ignored = tmp_path / "node_modules" / "dependency.test.ts"
    ignored.parent.mkdir()
    ignored.write_text("not supported syntax")
    assert find_modules([tmp_path], runner="vitest") == [test]
    assert vitest_identities([tmp_path]) == Counter({"a.test.ts::works": 1})
    mutate([test], "deleted", runner="vitest")
    assert not test.exists() and helper.exists() and ignored.exists()


def test_skip_and_empty_mutate_only_supported_registration(tmp_path: Path) -> None:
    path = tmp_path / "a.test.ts"
    path.write_text(SOURCE)
    mutate([path], "empty", runner="vitest")
    assert path.read_text() == SOURCE
    mutate([path], "skipped", runner="vitest")
    assert path.read_text() == SOURCE.replace('test("works"', 'test.skip("works"')


def test_unsupported_layout_refuses_without_source(tmp_path: Path) -> None:
    path = tmp_path / "a.test.ts"
    path.write_text('import {test as PRIVATE_CANARY} from "vitest";')
    with pytest.raises(UnsupportedTampering) as failure:
        find_modules([tmp_path], runner="vitest")
    assert "PRIVATE_CANARY" not in str(failure.value)


@pytest.mark.parametrize(
    "module,name",
    [
        ("../a.test.ts", "x"),
        ("/a.test.ts", "x"),
        ("a.test.ts", "x" * 240),
        ("a.test.ts", "unsafe\nname"),
        ("node_modules/a.test.ts", "x"),
    ],
)
def test_identity_limits(module: str, name: str) -> None:
    with pytest.raises(ValueError):
        vitest_identity(module, name)
