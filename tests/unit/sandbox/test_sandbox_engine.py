from __future__ import annotations

from pathlib import Path

import pytest

from patchground.sandbox import EngineUnavailable, Limits, build_image, run_check


@pytest.fixture
def no_engine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DOCKER_HOST", f"unix://{tmp_path}/no-such.sock")
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)


@pytest.mark.usefixtures("no_engine")
def test_build_without_engine(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM scratch\n")
    with pytest.raises(EngineUnavailable):
        build_image(dockerfile, name="x")


@pytest.mark.usefixtures("no_engine")
def test_run_without_engine(tmp_path: Path) -> None:
    with pytest.raises(EngineUnavailable):
        run_check("sha256:0", [tmp_path], "true")


def test_build_rejects_bad_name(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM scratch\n")
    with pytest.raises(ValueError, match="invalid image name"):
        build_image(dockerfile, name="Bad Name")


@pytest.mark.parametrize("field", ["cpus", "memory_bytes", "pids", "timeout_seconds"])
def test_limits_must_be_positive(field: str) -> None:
    with pytest.raises(ValueError, match="positive"):
        Limits(**{field: 0})


def test_default_limits_match_contract() -> None:
    assert Limits() == Limits(cpus=2.0, memory_bytes=2 * 1024**3, pids=512, timeout_seconds=600.0)
