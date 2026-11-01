"""Discover, verify and index community challenge packs.

Run by `.github/workflows/registry.yml`; see `registry/SPEC.md`. Standard library plus the
installed `patchground` package only.

    uv run python registry/crawl.py            # full run: discover, validate, write index/status
    uv run python registry/crawl.py --dry-run  # discover + policy checks only; no Docker, no writes
    uv run python registry/crawl.py --source https://github.com/x/y.git   # one source, no discovery

Pipeline per source: clone at the default-branch head with an isolated git environment ->
policy checks (manifests load with patchground.spec, every listed challenge exists, license and
provenance declared, no services, size limits, secret scan) -> `pgnd validate --json --no-write`
for every challenge -> an entry in index.json (verified) or status.json (failed/error).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REGISTRY = Path(__file__).resolve().parent
INDEX_PATH = REGISTRY / "index.json"
STATUS_PATH = REGISTRY / "status.json"
SOURCES_PATH = REGISTRY / "sources.yaml"

TOPIC = "patchground-pack"
REVERIFY_AFTER = timedelta(days=30)
MAX_FRESH_VALIDATIONS = 20
CLONE_TIMEOUT_S = 300
VALIDATE_TIMEOUT_S = 1800
MAX_BYTES = 100 * 1024 * 1024
MAX_FILES = 10_000
MAX_PACKS_PER_HOST_PAGE = 100

# The only challenge fields that ever leave the pack. Mirrors web/scripts/catalog.mjs.
PUBLIC_CHALLENGE_FIELDS = (
    "id",
    "title",
    "summary",
    "type",
    "languages",
    "tags",
    "difficulty",
    "timebox_minutes",
    "provenance",
)
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
GITHUB_URL = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")


def now() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


# ----------------------------------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------------------------------


@dataclass
class Source:
    url: str
    host: str  # "github" | "git"
    discovered_by: str  # "topic" | "sources.yaml"
    stars: int = 0
    forks: int = 0
    pushed_at: str | None = None
    homepage: str | None = None


@dataclass
class Seen:
    source: str
    commit: str | None
    checked_at: str
    result: str  # verified | failed | error | skipped
    failed_step: str | None = None
    failing_challenge: str | None = None
    detail: str | None = None
    name: str | None = None


@dataclass
class PackEntry:
    name: str
    source: str
    host: str
    commit: str
    verified_at: str
    version: str
    description: str
    challenges: list[dict[str, Any]]
    stars: int = 0
    forks: int = 0
    pushed_at: str | None = None
    homepage: str | None = None
    first_seen: str | None = None
    tickets: dict[str, str] = field(default_factory=dict)


# ----------------------------------------------------------------------------------------------
# Discovery
# ----------------------------------------------------------------------------------------------


def github_api(path: str, token: str | None) -> Any:
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "patchground-registry",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed https host
        return json.load(response)


def discover_github(token: str | None) -> list[Source]:
    sources: list[Source] = []
    page = 1
    while True:
        query = urllib.parse.quote(f"topic:{TOPIC} fork:false archived:false")
        try:
            data = github_api(
                f"/search/repositories?q={query}&per_page={MAX_PACKS_PER_HOST_PAGE}&page={page}",
                token,
            )
        except urllib.error.URLError as exc:
            print(f"github discovery failed: {exc}", file=sys.stderr)
            break
        for repo in data.get("items", []):
            if repo.get("private") or repo.get("fork") or repo.get("archived"):
                continue
            sources.append(
                Source(
                    url=repo["clone_url"],
                    host="github",
                    discovered_by="topic",
                    stars=int(repo.get("stargazers_count", 0)),
                    forks=int(repo.get("forks_count", 0)),
                    pushed_at=repo.get("pushed_at"),
                    homepage=repo.get("html_url"),
                )
            )
        if len(data.get("items", [])) < MAX_PACKS_PER_HOST_PAGE or page >= 10:
            break
        page += 1
    return sources


def read_sources_yaml(path: Path = SOURCES_PATH) -> list[Source]:
    """Flat list of public https git URLs; comments and blanks ignored. No YAML library needed."""
    if not path.exists():
        return []
    out: list[Source] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.endswith(":"):
            continue
        url = line[2:].strip() if line.startswith("- ") else line
        if url.startswith("https://") and not any(c.isspace() for c in url):
            out.append(
                Source(
                    url=url,
                    host="github" if GITHUB_URL.match(url) else "git",
                    discovered_by="sources.yaml",
                )
            )
    return out


def dedupe(sources: list[Source]) -> list[Source]:
    by_url: dict[str, Source] = {}
    for source in sources:
        key = canonical(source.url)
        if key not in by_url or source.discovered_by == "topic":
            by_url[key] = source
    return list(by_url.values())


def canonical(url: str) -> str:
    url = url.strip().rstrip("/")
    return url[:-4].lower() if url.endswith(".git") else url.lower()


# ----------------------------------------------------------------------------------------------
# Clone + policy
# ----------------------------------------------------------------------------------------------


GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "/bin/false",
    "GIT_LFS_SKIP_SMUDGE": "1",
    "LC_ALL": "C",  # public status details stay in one language
    "PATH": os.environ.get("PATH", ""),
    "HOME": os.environ.get("HOME", tempfile.gettempdir()),
}


class PolicyError(Exception):
    def __init__(self, step: str, detail: str, challenge: str | None = None):
        super().__init__(detail)
        self.step, self.detail, self.challenge = step, detail, challenge


def scrub(detail: str, root: Path) -> str:
    """Public status must never carry runner paths; show pack-relative locations only."""
    return detail.replace(str(root) + "/", "").replace(str(root), "<pack>")[:300]


def clone(url: str, dest: Path) -> str:
    """Shallow clone of the default branch; returns the commit hash."""
    # Only https in production. PG_REGISTRY_ALLOW_FILE=1 lets tests feed a local file:// pack.
    allow_file = os.environ.get("PG_REGISTRY_ALLOW_FILE") == "1"
    extra = ["-c", "protocol.file.allow=always"] if allow_file else []
    cmd = [
        "git",
        "-c",
        "protocol.allow=never",
        "-c",
        "protocol.https.allow=always",
        *extra,
        "clone",
        "--depth",
        "1",
        "--no-tags",
        "--single-branch",
        "--no-recurse-submodules",
        url,
        str(dest),
    ]
    result = subprocess.run(
        cmd, env=GIT_ENV, capture_output=True, text=True, timeout=CLONE_TIMEOUT_S
    )
    if result.returncode != 0:
        raise PolicyError(
            "clone", (result.stderr.strip().splitlines() or ["git clone failed"])[-1][:200]
        )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=dest,
        env=GIT_ENV,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if head.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", head.stdout.strip()):
        raise PolicyError("clone", "could not resolve HEAD")
    shutil.rmtree(dest / ".git", ignore_errors=True)
    return head.stdout.strip()


def check_size(root: Path) -> None:
    files = 0
    total = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            raise PolicyError("policy", f"symlink not allowed: {path.relative_to(root)}")
        if path.is_file():
            files += 1
            total += path.stat().st_size
            if files > MAX_FILES or total > MAX_BYTES:
                raise PolicyError(
                    "policy",
                    f"pack exceeds limits ({MAX_FILES} files / {MAX_BYTES // 1024 // 1024} MiB)",
                )


def tool_env() -> dict[str, str]:
    """Environment for tools that touch untrusted packs: never forward the registry's token."""
    return {k: v for k, v in os.environ.items() if k not in {"GITHUB_TOKEN", "GH_TOKEN"}}


def secret_scan(root: Path) -> None:
    if shutil.which("gitleaks") is None:
        if os.environ.get("CI"):
            # CI must never list a pack it could not scan.
            raise PolicyError("policy", "secret scan could not run")
        print("gitleaks not installed; skipping secret scan", file=sys.stderr)
        return
    result = subprocess.run(
        ["gitleaks", "dir", str(root), "--no-banner", "--redact", "--exit-code", "9"],
        capture_output=True,
        text=True,
        timeout=300,
        env=tool_env(),
    )
    if result.returncode == 9:
        raise PolicyError("policy", "secret scan found credential-like content")
    if result.returncode not in (0,):
        raise PolicyError("policy", "secret scan could not run")


def load_manifests(root: Path) -> tuple[Any, list[Any]]:
    from patchground.spec import ManifestError, load_challenge, load_pack  # installed package

    try:
        pack = load_pack(root)
    except ManifestError as exc:
        raise PolicyError("manifest", f"pack.yaml: {exc.issues[0] if exc.issues else exc}") from exc
    except FileNotFoundError as exc:
        raise PolicyError("manifest", "pack.yaml not found at repository root") from exc
    challenges = []
    for cid in pack.manifest.challenges:
        folder = root / cid
        if not folder.is_dir():
            raise PolicyError(
                "manifest", f"challenge folder '{cid}' listed in pack.yaml does not exist", cid
            )
        try:
            challenge = load_challenge(folder)
        except ManifestError as exc:
            raise PolicyError(
                "manifest", f"{cid}/challenge.yaml: {exc.issues[0] if exc.issues else exc}", cid
            ) from exc
        m = challenge.manifest
        if m.id != cid:
            raise PolicyError(
                "manifest", f"challenge id '{m.id}' does not match folder '{cid}'", cid
            )
        if getattr(m, "content_license", None) in (None, ""):
            raise PolicyError("policy", "content_license must be declared", cid)
        if getattr(m, "provenance", None) in (None, ""):
            raise PolicyError("policy", "provenance must be declared", cid)
        services = getattr(getattr(m, "environment", None), "services", None)
        if services:
            raise PolicyError(
                "policy",
                "environment.services must be empty (multi-container is not supported)",
                cid,
            )
        challenges.append(challenge)
    return pack, challenges


def public_fields(manifest: Any) -> dict[str, Any]:
    data = manifest.model_dump(mode="json")
    out = {k: data[k] for k in PUBLIC_CHALLENGE_FIELDS if k in data}
    for key in ("languages", "tags"):
        out[key] = [str(v) for v in out.get(key, [])]
    return out


# ----------------------------------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------------------------------


def pgnd_validate(folder: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["pgnd", "validate", "--json", "--no-write", str(folder)],
        capture_output=True,
        text=True,
        timeout=VALIDATE_TIMEOUT_S,
        env=tool_env(),
    )
    try:
        report = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        report = {}
    if result.returncode == 2 or "valid" not in report:
        raise RuntimeError(
            report.get("message") or (result.stderr.strip()[-200:] or "validator did not run")
        )
    return report


# ----------------------------------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------------------------------


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def ticket_url(source: Source, commit: str, cid: str) -> str:
    match = GITHUB_URL.match(source.url)
    if match:
        return f"https://github.com/{match.group(1)}/{match.group(2)}/blob/{commit}/{cid}/TICKET.md"
    return source.url


def process(
    source: Source, previous: PackEntry | None, *, dry_run: bool, budget: dict[str, int]
) -> tuple[PackEntry | None, Seen]:
    checked = iso(now())
    workdir = Path(tempfile.mkdtemp(prefix="pg-registry-"))
    try:
        try:
            commit = clone(source.url, workdir / "pack")
        except (PolicyError, subprocess.TimeoutExpired) as exc:
            detail = exc.detail if isinstance(exc, PolicyError) else "clone timed out"
            return previous, Seen(source.url, None, checked, "error", "clone", None, detail)
        root = workdir / "pack"

        if (
            previous
            and previous.commit == commit
            and (now() - datetime.fromisoformat(previous.verified_at)) < REVERIFY_AFTER
        ):
            previous.stars, previous.forks, previous.pushed_at = (
                source.stars,
                source.forks,
                source.pushed_at,
            )
            return previous, Seen(
                source.url,
                commit,
                checked,
                "skipped",
                None,
                None,
                "unchanged since last verification",
                previous.name,
            )

        try:
            check_size(root)
            pack, challenges = load_manifests(root)
            secret_scan(root)
        except PolicyError as exc:
            return None, Seen(
                source.url,
                commit,
                checked,
                "failed",
                exc.step,
                exc.challenge,
                scrub(exc.detail, root),
            )

        name = pack.manifest.name
        if dry_run:
            return None, Seen(
                source.url, commit, checked, "skipped", None, None, "dry run: policy passed", name
            )
        if budget["fresh"] <= 0:
            return previous, Seen(
                source.url,
                commit,
                checked,
                "skipped",
                None,
                None,
                "validation budget exhausted; retried next run",
                name,
            )
        budget["fresh"] -= 1

        public: list[dict[str, Any]] = []
        tickets: dict[str, str] = {}
        for challenge in challenges:
            cid = challenge.manifest.id
            try:
                report = pgnd_validate(challenge.root)
            except (RuntimeError, subprocess.TimeoutExpired) as exc:
                detail = (
                    "validation timed out"
                    if isinstance(exc, subprocess.TimeoutExpired)
                    else str(exc)
                )
                return previous, Seen(
                    source.url, commit, checked, "error", "validate", cid, detail, name
                )
            if not report.get("valid"):
                return None, Seen(
                    source.url,
                    commit,
                    checked,
                    "failed",
                    report.get("failed_step") or "validate",
                    cid,
                    "pgnd validate failed",
                    name,
                )
            public.append(public_fields(challenge.manifest))
            tickets[cid] = ticket_url(source, commit, cid)

        entry = PackEntry(
            name=name,
            source=source.url,
            host=source.host,
            commit=commit,
            verified_at=checked,
            version=str(pack.manifest.version),
            description=pack.manifest.description,
            challenges=public,
            stars=source.stars,
            forks=source.forks,
            pushed_at=source.pushed_at,
            homepage=source.homepage,
            first_seen=previous.first_seen if previous else checked,
            tickets=tickets,
        )
        return entry, Seen(
            source.url, commit, checked, "verified", None, None, f"{len(public)} challenges", name
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def write_if_changed(path: Path, document: dict[str, Any]) -> None:
    """Keep the old file (and its timestamp) when only `generated_at` would change.

    Otherwise every scheduled run would commit a new timestamp to the repository."""

    def content(doc: Any) -> Any:
        return (
            {k: v for k, v in doc.items() if k != "generated_at"} if isinstance(doc, dict) else doc
        )

    if content(load_json(path, None)) == content(document):
        return
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def run(*, dry_run: bool, only: str | None, token: str | None) -> int:
    sources = (
        [Source(only, "github" if GITHUB_URL.match(only) else "git", "cli")]
        if only
        else dedupe(discover_github(token) + read_sources_yaml())
    )
    index = load_json(INDEX_PATH, {"packs": []})
    previous_by_source = {canonical(p["source"]): PackEntry(**p) for p in index.get("packs", [])}

    budget = {"fresh": MAX_FRESH_VALIDATIONS}
    packs: dict[str, PackEntry] = {}
    seen: list[Seen] = []
    if only:
        # A single-source run updates one entry; every other pack and status row is kept as is.
        target = canonical(only)
        for key, entry in previous_by_source.items():
            if key != target:
                packs[entry.name] = entry
        status = load_json(STATUS_PATH, {"seen": []})
        seen = [Seen(**s) for s in status.get("seen", []) if canonical(s["source"]) != target]
    for source in sorted(sources, key=lambda s: (-s.stars, s.url)):
        entry, record = process(
            source, previous_by_source.get(canonical(source.url)), dry_run=dry_run, budget=budget
        )
        print(
            f"{record.result:9} {source.url} {record.failed_step or ''} "
            f"{record.detail or ''}".rstrip()
        )
        if entry is not None:
            if entry.name in packs:  # first-seen wins on name collisions
                record = Seen(
                    source.url,
                    record.commit,
                    record.checked_at,
                    "failed",
                    "policy",
                    None,
                    f"pack name '{entry.name}' already taken by {packs[entry.name].source}",
                    entry.name,
                )
            else:
                packs[entry.name] = entry
        seen.append(record)

    if dry_run:
        return 0
    stamp = iso(now())
    write_if_changed(
        INDEX_PATH,
        {
            "schema": "patchground-registry-index/1",
            "generated_at": stamp,
            "public_fields": list(PUBLIC_CHALLENGE_FIELDS),
            "packs": [asdict(p) for p in sorted(packs.values(), key=lambda p: p.name)],
        },
    )
    write_if_changed(
        STATUS_PATH,
        {
            "schema": "patchground-registry-status/1",
            "generated_at": stamp,
            "topic": TOPIC,
            "seen": [asdict(s) for s in sorted(seen, key=lambda s: s.source)],
        },
    )
    print(f"index: {len(packs)} verified packs; status: {len(seen)} sources seen")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="discover + policy only; no Docker, no writes"
    )
    parser.add_argument(
        "--source", help="process exactly this public https git URL and skip discovery"
    )
    args = parser.parse_args(argv)
    return run(dry_run=args.dry_run, only=args.source, token=os.environ.get("GITHUB_TOKEN"))


if __name__ == "__main__":
    sys.exit(main())
