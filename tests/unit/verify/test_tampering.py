"""The adapter transforms source without executing authored Python."""

import ast

import pytest

from patchground.verify.tampering import (
    UnsupportedTampering,
    mutate,
    supports_pytest,
)
from patchground.verify.tampering import (
    test_modules as find_modules,
)


@pytest.mark.parametrize(
    "command",
    [
        "pytest -q",
        "pytest-3 --junitxml=$PG_RESULTS/junit.xml",
        "python -m pytest",
        "python3 -m pytest",
    ],
)
def test_supported_commands(command):
    assert supports_pytest(command)


@pytest.mark.parametrize(
    "command",
    [
        "",
        "npm test",
        "./test.sh",
        "uv run pytest",
        "pytest; echo done",
        "pytest && echo done",
        "pytest | tee output",
        "pytest > output",
        "pytest 'unterminated",
        "MODE=x pytest",
    ],
)
def test_unsupported_commands(command):
    assert not supports_pytest(command)


def test_selects_only_conventional_modules(tmp_path):
    for name in (
        "test_a.py",
        "a_test.py",
        "conftest.py",
        "helpers.py",
        "code.py",
        "test_data.json",
    ):
        (tmp_path / name).write_text("# fixture\n")
    (tmp_path / "test_a.py").write_text("def test_a():\n    pass\n")
    (tmp_path / "a_test.py").write_text("class TestA:\n    async def test_a(self):\n        pass\n")
    (tmp_path / "test_helpers.py").write_text("def helper():\n    pass\n")
    modules = find_modules([tmp_path])
    assert [path.name for path in modules] == ["a_test.py", "test_a.py"]
    mutate(modules, "deleted")
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "code.py",
        "conftest.py",
        "helpers.py",
        "test_data.json",
        "test_helpers.py",
    ]


def test_skip_preserves_bytes_and_marks_without_executing(tmp_path):
    path = tmp_path / "test_sample.py"
    source = (
        b"# coding: latin-1\n# caf\xe9\n"
        b"raise RuntimeError('must never execute on the host')\n"
        b"pytestmark = []\n_patchground_anti_gaming_pytest = 1\n"
        b"def test_sample():\n    assert True\n"
    )
    path.write_bytes(source)
    mutate([path], "skipped")
    after = path.read_bytes()
    assert after.startswith(source)
    assert b"import pytest as _patchground_anti_gaming_pytest_\n" in after
    assert b"mark.skip" in after
    assert b"globals().get('pytestmark', [])" in after
    ast.parse(after.decode("latin-1"))


def test_invalid_python_is_unverified_without_echoing_source(tmp_path):
    path = tmp_path / "test_bad.py"
    path.write_text("PRIVATE-SYNTHETIC-MARKER = (\n")
    with pytest.raises(UnsupportedTampering) as error:
        mutate([path], "skipped")
    assert "PRIVATE-SYNTHETIC-MARKER" not in str(error.value)
