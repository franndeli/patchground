from __future__ import annotations

import io
import os
import tarfile
from pathlib import Path

import pytest

from patchground.sandbox import JUnitError, SandboxError
from patchground.sandbox.build import context_hash
from patchground.sandbox.run import _extract_single_file, build_seed_tar


def _write(path: Path, content: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(mode)


def _members(data: bytes) -> dict[str, tarfile.TarInfo]:
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        return {m.name: m for m in tar.getmembers()}


def _read(data: bytes, name: str) -> bytes:
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        fh = tar.extractfile(name)
        assert fh is not None
        return fh.read()


def test_tar_ownership_root_entry_and_modes(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    _write(ws / "app.py", "print('hi')\n")
    _write(ws / "run.sh", "#!/bin/sh\n", 0o755)
    _write(ws / "pkg" / "mod.py", "x = 1\n")
    members = _members(build_seed_tar([ws]))

    assert list(members) == [
        "workspace",
        "workspace/app.py",
        "workspace/pkg",
        "workspace/pkg/mod.py",
        "workspace/run.sh",
        "results",
    ]
    for root in (members["workspace"], members["results"]):
        assert root.isdir() and root.mode == 0o755
    for m in members.values():
        assert (m.uid, m.gid, m.uname, m.gname) == (1000, 1000, "", "")
        assert m.isdir() or m.isreg()
    assert members["workspace/run.sh"].mode == 0o755
    assert members["workspace/app.py"].mode == 0o644
    assert members["workspace/pkg"].isdir()


def test_tar_strips_special_mode_bits(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    _write(ws / "suid", "x", 0o4755)
    assert _members(build_seed_tar([ws]))["workspace/suid"].mode == 0o755


def test_layers_apply_in_order_and_merge_directories(tmp_path: Path) -> None:
    ws, hidden = tmp_path / "ws", tmp_path / "hidden"
    _write(ws / "tests" / "test_public.py", "public")
    _write(hidden / "tests" / "test_hidden.py", "hidden")
    data = build_seed_tar([ws, hidden])
    names = list(_members(data))
    assert names == [
        "workspace",
        "workspace/tests",
        "workspace/tests/test_hidden.py",
        "workspace/tests/test_public.py",
        "results",
    ]
    assert _read(data, "workspace/tests/test_hidden.py") == b"hidden"
    assert _read(data, "workspace/tests/test_public.py") == b"public"


@pytest.mark.parametrize("clash", ["file-file", "dir-file", "file-dir"])
def test_layer_clash_is_an_error(tmp_path: Path, clash: str) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    first, second = clash.split("-")
    for layer, kind in ((a, first), (b, second)):
        if kind == "file":
            _write(layer / "x", "content")
        else:
            _write(layer / "x" / "inner", "content")
    with pytest.raises(SandboxError, match="more than one layer"):
        build_seed_tar([a, b])


def test_symlink_is_rejected(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    _write(ws / "ok.txt", "ok")
    (ws / "escape").symlink_to("/etc/passwd")
    with pytest.raises(SandboxError, match="symlink"):
        build_seed_tar([ws])


def test_symlinked_directory_is_rejected(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "outside").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(SandboxError, match="symlink"):
        build_seed_tar([ws])


def test_fifo_is_rejected(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    os.mkfifo(ws / "pipe")
    with pytest.raises(SandboxError, match="special file"):
        build_seed_tar([ws])


def test_layer_must_be_a_directory(tmp_path: Path) -> None:
    _write(tmp_path / "file", "x")
    with pytest.raises(SandboxError):
        build_seed_tar([tmp_path / "file"])
    with pytest.raises(SandboxError):
        build_seed_tar([tmp_path / "missing"])


def test_no_layers_gives_empty_roots() -> None:
    assert list(_members(build_seed_tar([]))) == ["workspace", "results"]


def _single_file_tar(info: tarfile.TarInfo, content: bytes = b"") -> list[bytes]:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info.size = len(content) if info.isreg() else 0
        tar.addfile(info, io.BytesIO(content) if info.isreg() else None)
    data = buf.getvalue()
    return [data[:700], data[700:]]  # arrive in chunks, like get_archive


def test_extract_single_file() -> None:
    chunks = _single_file_tar(tarfile.TarInfo("junit.xml"), b"<testsuite/>")
    assert _extract_single_file(chunks, 1024) == b"<testsuite/>"


def test_extract_rejects_non_regular_member() -> None:
    link = tarfile.TarInfo("junit.xml")
    link.type = tarfile.SYMTYPE
    link.linkname = "/etc/passwd"
    with pytest.raises(JUnitError, match="regular file"):
        _extract_single_file(_single_file_tar(link), 1024)


def test_extract_rejects_oversized_file() -> None:
    chunks = _single_file_tar(tarfile.TarInfo("junit.xml"), b"x" * 2048)
    with pytest.raises(JUnitError, match="larger"):
        _extract_single_file(chunks, 1024)


def test_extract_rejects_garbage() -> None:
    with pytest.raises(JUnitError):
        _extract_single_file([b"definitely not a tar archive" * 40], 1024)


def test_context_hash_is_deterministic_and_content_sensitive(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    for root, order in (
        (a, ["Dockerfile", "req.txt", "sub/x"]),
        (b, ["sub/x", "req.txt", "Dockerfile"]),
    ):
        for name in order:
            _write(root / name, f"content of {name}")
    assert context_hash(a) == context_hash(b)
    assert len(context_hash(a)) == 64

    _write(b / "req.txt", "changed")
    assert context_hash(a) != context_hash(b)


def test_context_hash_sees_renames_and_modes(tmp_path: Path) -> None:
    _write(tmp_path / "f", "x")
    before = context_hash(tmp_path)
    (tmp_path / "f").chmod(0o755)
    after_chmod = context_hash(tmp_path)
    (tmp_path / "f").rename(tmp_path / "g")
    after_rename = context_hash(tmp_path)
    assert len({before, after_chmod, after_rename}) == 3
