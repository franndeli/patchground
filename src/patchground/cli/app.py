"""Typer application behind `patchground` / `pgnd`."""

import typer

from patchground import __version__
from patchground.cli.authoring import new
from patchground.cli.discovery import DiscoveryCommand, list_challenges, show
from patchground.cli.doctor import doctor
from patchground.cli.packs import app as packs_app
from patchground.cli.practice import RunCommand, hint, history, run, sessions
from patchground.cli.reports import report, submit
from patchground.cli.sessions import SessionCommand, check, reset, start, status
from patchground.cli.validate import validate

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
    """Practice real software engineering on broken repositories.

    `pgnd` is a short alias of `patchground`. New here? Run `pgnd doctor`, then
    `pgnd list --builtin` and `pgnd start <id>`.

    Sessions are kept in ~/patchground/sessions. To keep them elsewhere, set
    PATCHGROUND_SESSIONS_DIR to an absolute path.
    """


app.command("validate")(validate)
app.command("start", cls=SessionCommand)(start)
app.command("check", cls=SessionCommand)(check)
app.command("status", cls=SessionCommand)(status)
app.command("reset", cls=SessionCommand)(reset)
app.command("doctor", cls=DiscoveryCommand)(doctor)
app.command("list", cls=DiscoveryCommand)(list_challenges)
app.command("show", cls=DiscoveryCommand)(show)
app.command("new", cls=DiscoveryCommand)(new)
app.command("submit", cls=SessionCommand)(submit)
app.command("report", cls=SessionCommand)(report)
app.command("hint", cls=SessionCommand)(hint)
app.command("sessions", cls=SessionCommand)(sessions)
app.command("history", cls=SessionCommand)(history)
app.command("run", cls=RunCommand)(run)
app.add_typer(packs_app, name="pack")


def main() -> None:
    app()
