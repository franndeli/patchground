import hashlib
import subprocess
import zipfile
from pathlib import Path

from patchground import runner_assets
from patchground.authoring.create import _STARTERS

REPO = Path(__file__).resolve().parents[3]


def test_wheel_contains_all_template_assets(tmp_path: Path) -> None:
    result = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path)],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, "wheel build failed"
    wheels = list(tmp_path.glob("*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as wheel:
        names = set(wheel.namelist())
        for folder, relatives in _STARTERS.values():
            for relative in relatives:
                assert f"patchground/authoring/templates/{folder}/{relative}.tmpl" in names
        assert "patchground/runner_assets/__init__.py" in names
        for name, content in runner_assets.vitest_assets().items():
            assert wheel.read(f"patchground/runner_assets/{name}") == content
        for manifest in (REPO / "examples").glob("*/challenge.yaml"):
            challenge = manifest.parent
            for relative in (
                "challenge.yaml",
                "TICKET.md",
                "workspace",
                "environment",
                "checks",
                "solution",
                "debrief",
            ):
                path = challenge / relative
                sources = path.rglob("*") if path.is_dir() else [path]
                for source in sources:
                    if not source.is_file():
                        continue
                    packaged = f"patchground/catalog/{source.relative_to(REPO / 'examples')}"
                    assert packaged in names, packaged
                    assert (
                        hashlib.sha256(wheel.read(packaged)).digest()
                        == hashlib.sha256(source.read_bytes()).digest()
                    ), packaged
