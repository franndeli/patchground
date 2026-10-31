"""Command-line entry for the reusable validation Action.

Run as ``python -I -m patchground.automation``. Only fixed, path-free messages are emitted.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, NoReturn

from patchground.safeio import SafetyError, open_directory

ERROR_FORMAT = "patchground-automation-error"
USAGE_EXIT = 2
CANCEL_EXIT = 130


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _UsageError("invalid command-line arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="python -m patchground.automation", add_help=False, exit_on_error=False)
    parser.add_argument("--source", required=True)
    parser.add_argument("--directory", default=".")
    parser.add_argument("--base", default=None)
    parser.add_argument("--consent", action="store_true")
    parser.add_argument("--report", required=True)
    return parser


def _error_document(message: str) -> dict[str, Any]:
    return {"format": ERROR_FORMAT, "version": 1, "exit_code": USAGE_EXIT, "error": message}


def _reserve_report(report: str, source: Path) -> int:
    """Exclusively create the report in a pinned, link-free parent outside the checkout."""
    path = Path(report).absolute()
    if ".." in path.parts or path.name in {"", "."}:
        raise _UsageError("report path must name a file without '..' components")
    parent = path.parent
    if parent == source or source in parent.parents:
        raise _UsageError("report path must be outside the source checkout")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    try:
        with open_directory(parent, label="report") as pinned:
            return os.open(path.name, flags, 0o600, dir_fd=pinned)
    except FileExistsError:
        raise _UsageError("report file already exists") from None
    except (SafetyError, OSError):
        raise _UsageError("report location is unsafe or unavailable") from None


def _write(fd: int, document: dict[str, Any]) -> None:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _default_validate() -> Callable[..., Any]:
    from patchground.automation import validate_changes

    return validate_changes


def main(
    argv: Sequence[str] | None = None,
    *,
    validate: Callable[..., Any] | None = None,
) -> int:
    fd: int | None = None
    document: dict[str, Any] = _error_document("automation failed unexpectedly")
    code = USAGE_EXIT
    try:
        try:
            args = _parser().parse_args(argv)
        except argparse.ArgumentError:
            raise _UsageError("invalid command-line arguments") from None
        source = Path(args.source).resolve()
        if not source.is_dir():
            raise _UsageError("source is not a directory")
        fd = _reserve_report(args.report, source)
        run = validate or _default_validate()
        result = run(
            source,
            directory=args.directory,
            base=args.base or None,
            consent=args.consent,
        )
        document, code = result.to_dict(), int(result.exit_code)
        reserved, fd = fd, None
        _write(reserved, document)
        print(f"patchground validation finished with exit code {code}; report written")
        return code
    except _UsageError as exc:
        document, code = _error_document(str(exc)), USAGE_EXIT
    except KeyboardInterrupt:
        document, code = _error_document("cancelled"), CANCEL_EXIT
        document["exit_code"] = code
    except Exception as exc:  # report type only: messages may carry paths or source text
        document = _error_document(f"automation failed unexpectedly ({type(exc).__name__})")
        code = USAGE_EXIT
    finally:
        # Leaves no open descriptor behind; a repeated interrupt here is safe to ignore.
        pending, fd = fd, None
        if pending is not None:
            with contextlib.suppress(OSError, KeyboardInterrupt):
                _write(pending, document)
    print(json.dumps(document, sort_keys=True), file=sys.stderr)
    return code


def _terminate(signum: int, frame: Any) -> NoReturn:
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _terminate)
    sys.exit(main())
