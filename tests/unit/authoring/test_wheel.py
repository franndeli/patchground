import subprocess
import zipfile
from pathlib import Path

from patchground.authoring.create import TEMPLATE_FILES

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
        for relative in TEMPLATE_FILES:
            assert f"patchground/authoring/templates/python-debug/{relative}.tmpl" in names
