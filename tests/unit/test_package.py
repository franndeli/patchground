from typer.testing import CliRunner

from patchground import __version__
from patchground.cli.app import app


def test_version_flag() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__
