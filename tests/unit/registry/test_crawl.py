"""Registry crawler bookkeeping, with clone/validation replaced by fakes (no network, no Docker)."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "registry_crawl", Path(__file__).parents[3] / "registry" / "crawl.py"
)
assert SPEC and SPEC.loader
crawl = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = crawl
SPEC.loader.exec_module(crawl)


def entry(name: str, source: str) -> dict[str, object]:
    return {
        "name": name,
        "source": source,
        "host": "github",
        "commit": "a" * 40,
        "verified_at": "2026-10-01T00:00:00+00:00",
        "version": "0.1.0",
        "description": name,
        "challenges": [],
    }


@pytest.fixture
def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(crawl, "INDEX_PATH", tmp_path / "index.json")
    monkeypatch.setattr(crawl, "STATUS_PATH", tmp_path / "status.json")
    (tmp_path / "index.json").write_text(
        json.dumps(
            {
                "packs": [
                    entry("kept", "https://github.com/x/kept.git"),
                    entry("target", "https://github.com/x/target.git"),
                ]
            }
        )
    )
    (tmp_path / "status.json").write_text(
        json.dumps(
            {
                "seen": [
                    {
                        "source": "https://github.com/x/kept.git",
                        "commit": "a" * 40,
                        "checked_at": "2026-10-01T00:00:00+00:00",
                        "result": "verified",
                    }
                ]
            }
        )
    )
    return tmp_path


def test_single_source_run_keeps_every_other_pack(registry: Path, monkeypatch) -> None:
    def fail(source, previous, *, dry_run, budget):
        return None, crawl.Seen(source.url, "b" * 40, "2026-11-01T00:00:00+00:00", "failed")

    monkeypatch.setattr(crawl, "process", fail)
    assert crawl.run(dry_run=False, only="https://github.com/x/target.git", token=None) == 0
    index = json.loads((registry / "index.json").read_text())
    status = json.loads((registry / "status.json").read_text())
    assert [p["name"] for p in index["packs"]] == ["kept"]
    assert {s["source"]: s["result"] for s in status["seen"]} == {
        "https://github.com/x/kept.git": "verified",
        "https://github.com/x/target.git": "failed",
    }


def test_tools_touching_packs_never_receive_the_token(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghs-test-not-a-real-token")
    monkeypatch.setenv("GH_TOKEN", "ghs-test-not-a-real-token")
    env = crawl.tool_env()
    assert "GITHUB_TOKEN" not in env and "GH_TOKEN" not in env
    assert "GITHUB_TOKEN" not in crawl.GIT_ENV


def test_ci_never_lists_an_unscanned_pack(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(crawl.shutil, "which", lambda _: None)
    monkeypatch.setenv("CI", "true")
    with pytest.raises(crawl.PolicyError):
        crawl.secret_scan(tmp_path)


def test_an_unchanged_run_does_not_rewrite_the_index(tmp_path: Path) -> None:
    path = tmp_path / "index.json"
    crawl.write_if_changed(path, {"generated_at": "2026-11-01T00:00:00+00:00", "packs": []})
    before = path.read_bytes()
    crawl.write_if_changed(path, {"generated_at": "2026-11-02T00:00:00+00:00", "packs": []})
    assert path.read_bytes() == before
    crawl.write_if_changed(path, {"generated_at": "2026-11-02T00:00:00+00:00", "packs": [1]})
    assert json.loads(path.read_text())["packs"] == [1]
