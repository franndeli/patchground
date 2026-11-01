"""The Vitest adapter treats authored modules solely as syntax data."""

import operator
from collections.abc import MutableMapping
from pathlib import Path
from typing import cast

import pytest

from patchground.verify import vitest_adapter as adapter

IMPORTS = "import { test, expect } from 'vitest';\n"


def write(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "sample.test.ts"
    path.write_text(source, encoding="utf-8")
    return path


def test_definitions_offsets_assertions_and_inert_lookalikes(tmp_path: Path) -> None:
    source = (
        IMPORTS
        + """
const marker = "test('fake', () => {})";
const template = `describe('fake')`;
// test('comment', () => {})
test('café', async () => { expect(1).toBe(1); expect(2).not.toEqual(3); });
test('other', function () { expect(Promise.resolve(1)).resolves.toBe(1); });
"""
    )
    path = write(tmp_path, source)
    module = adapter.parse_module(path)
    assert set(module.definitions) == {"café", "other"}
    definition = module.definitions["café"]
    assert definition.assertions == 2
    assert module.definitions["other"].assertions == 1
    raw = path.read_bytes()
    assert raw[definition.start : definition.end].startswith(b"test('")
    assert raw[definition.callee_end - 4 : definition.callee_end] == b"test"
    assert raw[definition.end - 1 : definition.end] == b";"


def test_fingerprints_ignore_comments_and_spacing_preserve_syntax(tmp_path: Path) -> None:
    path = write(tmp_path, IMPORTS + "const helper = 1; test('one',()=>{expect(helper).toBe(1);});")
    first = adapter.parse_module(path)
    path.write_text(
        IMPORTS + "// trivia\nconst helper=1;\ntest( 'one', () => {expect( helper ).toBe(1)})"
    )
    second = adapter.parse_module(path)
    assert (
        first == second
        or first.definitions["one"].fingerprint == second.definitions["one"].fingerprint
    )
    assert first.helper_fingerprint == second.helper_fingerprint
    path.write_text(IMPORTS + "const helper=2; test('one',()=>{expect(helper).toBe(1)});")
    third = adapter.parse_module(path)
    assert third.helper_fingerprint != first.helper_fingerprint
    assert third.definitions["one"].fingerprint == first.definitions["one"].fingerprint


@pytest.mark.parametrize(
    "body",
    [
        "test('same',()=>{}); test('same',()=>{});",
        "test(name,()=>{});",
        r"te\u0073t('name',()=>{});",
        "test?.('name',()=>{});",
        "test<string>('name',()=>{});",
        "test('a',()=>{expect?.(1).toBe(1)});",
        "test(`name`,()=>{});",
        "test('a\\n',()=>{});",
        "test('line\\u0061',()=>{});",
        "test.each([1])('name',()=>{});",
        "test.skip('name',()=>{});",
        "describe('suite',()=>{test('name',()=>{})});",
        "for (const x of [1]) {test('name',()=>{})}",
        "if (true) test('name',()=>{});",
        "function register(){test('name',()=>{})}",
        "test('outer',()=>{test('inner',()=>{})});",
        "beforeEach(()=>{});",
        "const alias=test;",
        "const {test: alias}=thing;",
        "globalThis.test('a',()=>{});",
        "test('a',(expect)=>{expect(1).toBe(1)});",
        "test('a',()=>{const test=1});",
        "test('a',()=>{const alias=expect});",
        "test('a',()=>{expect(1)});",
        "test('a',()=>{} , 100);",
        "test('a', callback);",
        "test('',()=>{});",
        "test(' leading',()=>{});",
        "test('a\u2028b',()=>{});",
        "test('a',()=>{",
        "export const alias = test;",
    ],
)
def test_rejects_ambiguous_registration(tmp_path: Path, body: str) -> None:
    path = write(tmp_path, IMPORTS + body)
    with pytest.raises(adapter.UnsupportedVitest):
        adapter.parse_module(path)


@pytest.mark.parametrize(
    "imports",
    [
        "import {test as check,expect} from 'vitest';",
        "import {test,expect,beforeAll} from 'vitest';",
        "import * as vitest from 'vitest';",
        "import vitest from 'vitest';",
        "import {type test,expect} from 'vitest';",
        "import type {test,expect} from 'vitest';",
        "",
        "import {test} from 'vitest'; import {test,expect} from 'vitest';",
    ],
)
def test_rejects_noncanonical_imports(tmp_path: Path, imports: str) -> None:
    with pytest.raises(adapter.UnsupportedVitest):
        adapter.parse_module(write(tmp_path, imports + "test('a',()=>{expect(1).toBe(1)});"))


def test_select_and_skip_preserve_exact_material(tmp_path: Path) -> None:
    helper = IMPORTS + "const helper=1;\n"
    keep = "test('keep',()=>{expect(helper).toBe(1)});"
    remove = "test('remove',()=>{});"
    path = write(tmp_path, helper + keep + "\n" + remove)
    original = adapter.parse_module(path)
    adapter.select_tests(path, {"keep"})
    assert path.read_text() == helper + keep + "\n"
    selected = adapter.parse_module(path)
    assert selected.helper_fingerprint == original.helper_fingerprint
    assert selected.definitions["keep"].fingerprint == original.definitions["keep"].fingerprint
    adapter.skip_module(path)
    assert path.read_text() == helper + keep.replace("test(", "test.skip(", 1) + "\n"
    with pytest.raises(adapter.UnsupportedVitest):
        adapter.parse_module(path)


def test_missing_selection_does_not_write(tmp_path: Path) -> None:
    path = write(tmp_path, IMPORTS + "test('one',()=>{});")
    before = path.read_bytes()
    with pytest.raises(adapter.UnsupportedVitest):
        adapter.select_tests(path, {"absent"})
    assert path.read_bytes() == before


def test_empty_selection_preserves_helpers(tmp_path: Path) -> None:
    path = write(tmp_path, IMPORTS + "const helper=1;test('one',()=>{});")
    adapter.select_tests(path, set())
    assert path.read_text() == IMPORTS + "const helper=1;"
    adapter.skip_module(path)
    assert adapter.parse_module(path).definitions == {}


def test_size_encoding_depth_and_name_bounds(tmp_path: Path) -> None:
    path = write(tmp_path, " " * (adapter.MAX_SOURCE_BYTES + 1))
    with pytest.raises(adapter.UnsupportedVitest):
        adapter.parse_module(path)
    path.write_bytes(b"\xff")
    with pytest.raises(adapter.UnsupportedVitest):
        adapter.parse_module(path)
    path.write_text("const a=" + "(" * 300 + "1" + ")" * 300)
    with pytest.raises(adapter.UnsupportedVitest):
        adapter.parse_module(path)
    path.write_text(IMPORTS + "test('" + "a" * 201 + "',()=>{});")
    with pytest.raises(adapter.UnsupportedVitest):
        adapter.parse_module(path)


def test_source_is_never_executed(tmp_path: Path) -> None:
    marker = tmp_path / "execution-marker"
    path = write(
        tmp_path,
        IMPORTS
        + f"require('node:fs').writeFileSync({str(marker)!r}, 'executed');"
        + "test('one',()=>{throw new Error('inert')});",
    )
    assert adapter.parse_module(path).definitions["one"].assertions == 0
    adapter.skip_module(path)
    assert not marker.exists()


@pytest.mark.parametrize(
    ("name", "supported"),
    [("a.test.ts", True), ("test.ts", False), ("a.test.tsx", False), ("a.test.js", False)],
)
def test_filenames(name: str, supported: bool) -> None:
    assert adapter.is_test_filename(name) is supported


def test_module_definitions_refuse_mutation_and_detach_from_input(tmp_path: Path) -> None:
    module = adapter.parse_module(write(tmp_path, IMPORTS + "test('one',()=>{});"))
    mutable = cast(MutableMapping[str, adapter.TestDefinition], module.definitions)
    with pytest.raises(TypeError):
        operator.setitem(mutable, "other", module.definitions["one"])
    with pytest.raises(TypeError):
        operator.delitem(mutable, "one")
    definitions = dict(module.definitions)
    copied = adapter.TestModule(definitions, module.helper_fingerprint)
    definitions.clear()
    assert set(copied.definitions) == {"one"}
