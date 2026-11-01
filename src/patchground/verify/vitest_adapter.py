"""Bounded, non-executing TypeScript syntax analysis for the canonical Vitest runner."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

MAX_SOURCE_BYTES = 1024 * 1024
_MAX_NODES = 200_000
_MAX_DEPTH = 256
_LANGUAGE = Language(tree_sitter_typescript.language_typescript())
_FORBIDDEN = frozenset(
    {
        "describe",
        "suite",
        "it",
        "beforeAll",
        "afterAll",
        "beforeEach",
        "afterEach",
    }
)


class UnsupportedVitest(Exception):
    """Unsupported or ambiguous syntax; diagnostics never contain authored source."""


@dataclass(frozen=True)
class TestDefinition:
    name: str
    fingerprint: str
    start: int
    end: int
    callee_end: int
    assertions: int


@dataclass(frozen=True)
class TestModule:
    definitions: Mapping[str, TestDefinition]
    helper_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "definitions", MappingProxyType(dict(self.definitions)))


def is_test_filename(name: str) -> bool:
    return name.endswith(".test.ts")


def _walk(root: Node) -> list[Node]:
    result: list[Node] = []
    stack = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        if depth > _MAX_DEPTH or len(result) >= _MAX_NODES:
            raise UnsupportedVitest("Module syntax exceeds analysis bounds")
        result.append(node)
        stack.extend((child, depth + 1) for child in reversed(node.children))
    return result


def _literal(node: Node) -> str:
    raw = node.text
    if node.type != "string" or raw is None:
        raise UnsupportedVitest("Test names must be literal strings")
    # Deliberately reject JS escape syntax rather than approximate its decoding.
    if b"\\" in raw:
        raise UnsupportedVitest("Escaped literals are unsupported")
    try:
        value = raw[1:-1].decode("utf-8")
    except UnicodeError as exc:
        raise UnsupportedVitest("Invalid source encoding") from exc
    return value


def _fingerprint(nodes: list[Node]) -> str:
    digest = hashlib.sha256()
    for root in nodes:
        for node in _walk(root):
            if node.type in {"comment", ";"}:
                continue
            # Token text plus node kinds preserves syntax without whitespace or comments.
            if not node.children:
                digest.update(
                    json.dumps(
                        [node.type, (node.text or b"").decode("utf-8")], ensure_ascii=True
                    ).encode()
                )
            else:
                digest.update(node.type.encode() + b"\0")
    return digest.hexdigest()


def _read(path: Path) -> bytes:
    with path.open("rb") as stream:
        source = stream.read(MAX_SOURCE_BYTES + 1)
    if len(source) > MAX_SOURCE_BYTES:
        raise UnsupportedVitest("Module exceeds 1 MiB")
    try:
        source.decode("utf-8")
    except UnicodeError as exc:
        raise UnsupportedVitest("Invalid source encoding") from exc
    return source


def parse_module(path: Path) -> TestModule:
    source = _read(path)
    root = Parser(_LANGUAGE).parse(source).root_node
    nodes = _walk(root)
    if root.has_error:
        raise UnsupportedVitest("Invalid TypeScript syntax")
    allowed: set[int] = set()
    imported: set[str] = set()
    for statement in root.named_children:
        if statement.type != "import_statement":
            continue
        module = statement.child_by_field_name("source")
        if module is None or _literal(module) != "vitest":
            continue
        if any(n.type == "type" for n in _walk(statement)):
            raise UnsupportedVitest("Type-only Vitest imports are unsupported")
        specifiers = [n for n in _walk(statement) if n.type == "import_specifier"]
        if not specifiers:
            raise UnsupportedVitest("Canonical named Vitest imports required")
        for specifier in specifiers:
            name = specifier.child_by_field_name("name")
            if (
                name is None
                or specifier.child_by_field_name("alias") is not None
                or name.text not in {b"test", b"expect"}
                or any(n.type == "type" for n in specifier.children)
            ):
                raise UnsupportedVitest("Unsupported Vitest import")
            value = (name.text or b"").decode()
            if value in imported:
                raise UnsupportedVitest("Duplicate Vitest import")
            imported.add(value)
            allowed.add(name.id)
        if any(
            n.type in {"namespace_import", "identifier"} and n.id not in allowed
            for n in _walk(statement)
        ):
            raise UnsupportedVitest("Unsupported Vitest import")
    definitions: dict[str, TestDefinition] = {}
    statements: set[int] = set()
    for statement in root.named_children:
        if statement.type != "expression_statement" or len(statement.named_children) != 1:
            continue
        call = statement.named_children[0]
        callee = call.child_by_field_name("function")
        if call.type != "call_expression" or callee is None or callee.text != b"test":
            continue
        if any(n.type in {"type_arguments", "optional_chain", "?."} for n in call.children):
            raise UnsupportedVitest("Unsupported test call syntax")
        arguments = call.child_by_field_name("arguments")
        args = (
            []
            if arguments is None
            else [n for n in arguments.named_children if n.type != "comment"]
        )
        if (
            "test" not in imported
            or len(args) != 2
            or args[1].type not in {"arrow_function", "function_expression"}
        ):
            raise UnsupportedVitest("Unsupported test registration")
        test_name = _literal(args[0])
        if (
            not test_name
            or len(test_name) > 200
            or not test_name.isprintable()
            or test_name.strip() != test_name
        ):
            raise UnsupportedVitest("Test identity is not safely representable")
        if test_name in definitions:
            raise UnsupportedVitest("Duplicate test identity")
        allowed.add(callee.id)
        statements.add(statement.id)
        callback = args[1]
        assertions = 0
        for node in _walk(callback):
            if node.type != "call_expression":
                continue
            fn = node.child_by_field_name("function")
            if fn is None or fn.type != "member_expression":
                continue
            obj = fn.child_by_field_name("object")
            while obj is not None and obj.type == "member_expression":
                prop = obj.child_by_field_name("property")
                if prop is None or prop.text not in {b"not", b"resolves", b"rejects"}:
                    break
                obj = obj.child_by_field_name("object")
            if obj is not None and obj.type == "call_expression":
                expect = obj.child_by_field_name("function")
                if expect is not None and expect.type == "identifier" and expect.text == b"expect":
                    if any(n.type in {"optional_chain", "?."} for n in _walk(node)):
                        raise UnsupportedVitest("Optional assertion calls are unsupported")
                    allowed.add(expect.id)
                    assertions += 1
        definitions[test_name] = TestDefinition(
            test_name,
            _fingerprint([statement]),
            statement.start_byte,
            statement.end_byte,
            callee.end_byte,
            assertions,
        )
    for node in nodes:
        if node.type not in {
            "identifier",
            "shorthand_property_identifier",
            "shorthand_property_identifier_pattern",
            "property_identifier",
        }:
            continue
        if b"\\" in (node.text or b""):
            raise UnsupportedVitest("Escaped identifiers are unsupported")
        text = (node.text or b"").decode("utf-8")
        if text in _FORBIDDEN or (text in {"test", "expect"} and node.id not in allowed):
            raise UnsupportedVitest("Registration symbols are shadowed, leaked or unsupported")
    if "expect" not in imported and any(d.assertions for d in definitions.values()):
        raise UnsupportedVitest("Canonical expect import required")
    helpers = [n for n in root.named_children if n.id not in statements and n.type != "comment"]
    return TestModule(definitions, _fingerprint(helpers))


def skip_module(path: Path) -> None:
    module = parse_module(path)
    source = _read(path)
    for definition in sorted(module.definitions.values(), key=lambda d: d.callee_end, reverse=True):
        source = source[: definition.callee_end] + b".skip" + source[definition.callee_end :]
    path.write_bytes(source)


def select_tests(path: Path, names: set[str]) -> None:
    module = parse_module(path)
    if not names <= module.definitions.keys():
        raise UnsupportedVitest("Selected test identity is missing")
    source = _read(path)
    for definition in sorted(module.definitions.values(), key=lambda d: d.start, reverse=True):
        if definition.name not in names:
            source = source[: definition.start] + source[definition.end :]
    path.write_bytes(source)
