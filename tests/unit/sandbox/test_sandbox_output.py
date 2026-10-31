"""Unit tests for command output sanitizing and argv validation (no engine needed)."""

from __future__ import annotations

from pathlib import Path

import pytest

from patchground.sandbox import SandboxError, run_command
from patchground.sandbox.run import MAX_OUTPUT_TAIL_BYTES, CommandResult, sanitize_output


def test_plain_text_is_unchanged() -> None:
    assert sanitize_output(b"hello\n\tworld\n") == "hello\n\tworld\n"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"\x1b[31mred\x1b[0m", "red"),
        (b"a\x1b[2J\x1b[Hb", "ab"),
        (b"\x1b]0;evil title\x07x", "x"),
        (b"\x1b]8;;http://example.invalid\x1b\\link\x1b]8;;\x1b\\", "link"),
        (b"\x1bPsixel\x1b\\x", "x"),
        (b"\x1b]0;unterminated", ""),
        (b"line one\r\nline two\roverwrite", "line one\nline twooverwrite"),
        (b"bell\x07nul\x00del\x7f", "bellnuldel"),
        (b"c1\xc2\x9bcsi", "c1csi"),
        (b"trailing\x1b", "trailing"),
    ],
)
def test_control_sequences_are_removed(raw: bytes, expected: str) -> None:
    assert sanitize_output(raw) == expected


def test_invalid_utf8_is_replaced() -> None:
    assert sanitize_output(b"a\xffb") == "a\ufffdb"


def test_tail_keeps_the_end_within_the_byte_bound() -> None:
    raw = b"head-" + b"x" * (MAX_OUTPUT_TAIL_BYTES * 3) + b"-end"
    out = sanitize_output(raw)
    assert len(out.encode()) == MAX_OUTPUT_TAIL_BYTES
    assert out.endswith("-end") and "head" not in out


def test_tail_never_splits_a_multibyte_character() -> None:
    out = sanitize_output("é".encode() * MAX_OUTPUT_TAIL_BYTES)
    assert len(out.encode()) <= MAX_OUTPUT_TAIL_BYTES
    assert set(out) == {"é"}


def test_result_is_always_tail_only() -> None:
    assert CommandResult(0, None, "").output_tail_only is True


@pytest.mark.parametrize("argv", [[], [""], ["echo", "a\0b"]])
def test_invalid_argv_is_rejected_before_touching_the_engine(
    argv: list[str], tmp_path: Path
) -> None:
    with pytest.raises(SandboxError):
        run_command("sha256:" + "0" * 64, [tmp_path], argv)
