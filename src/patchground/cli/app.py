"""Typer application behind `patchground` / `pgnd`."""

import typer

from patchground import __version__

app = typer.Typer(name="patchground", no_args_is_help=True, add_completion=False)


def _version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def root(
    version: bool = typer.Option(
        False, "--version", callback=_version, is_eager=True, help="Show the version and exit."
    ),
) -> None:
    """Practice real software engineering on broken repositories."""


def main() -> None:
    app()
