#!/usr/bin/env bash
# Release-candidate check: the full learner loop for every built-in challenge, driven only through
# an installed wheel in a fresh virtual environment. Run from the repository root with Docker up.
#
#   bash docs/evaluations/release-candidate-check.sh
#
# For each challenge: start → check (must fail) → apply the reference patch to the workspace →
# check (must pass) → hint → history → submit (must pass, regression not required) → report.
# Then: the four `new` starters validate, a local pack installs with consent and starts, and
# reset restores a workspace. Nothing here touches ~/patchground.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="$(mktemp -d /tmp/pg-rc.XXXXXX)"
WORK="$(cd "$WORK" && pwd -P)"   # /tmp is a symlink on macOS; pack sources must be canonical
export PATCHGROUND_SESSIONS_DIR="$WORK/sessions"

trap 'chmod -R u+w "$WORK" 2>/dev/null || true; rm -rf "$WORK"' EXIT

say() { printf '\n== %s\n' "$*"; }
need() { # need <expected-exit> <description> -- command...
  local expected="$1" what="$2"; shift 3
  set +e; "$@" >"$WORK/last.out" 2>&1; local code=$?; set -e
  if [ "$code" -ne "$expected" ]; then
    echo "FAIL: $what (exit $code, expected $expected)"; tail -40 "$WORK/last.out"; exit 1
  fi
  echo "ok: $what"
}
json() { python3 -c "import json,sys; d=json.load(open('$WORK/last.out')); print($1)"; }

say "build and install the wheel"
(cd "$ROOT" && uv build --wheel -o "$WORK/dist" >/dev/null 2>&1)
uv venv -q --python 3.12 "$WORK/venv"
VIRTUAL_ENV="$WORK/venv" uv pip install -q "$WORK"/dist/*.whl
P="$WORK/venv/bin/pgnd"
need 0 "pgnd --version" -- "$P" --version
need 0 "pgnd doctor" -- "$P" doctor --json
need 0 "pgnd list --builtin" -- "$P" list --builtin --json
IDS="$(json "' '.join(c['id'] for c in d['challenges'])")"
echo "built-in: $IDS"

for id in $IDS; do
  say "challenge $id"
  mkdir -p "$WORK/play" && cd "$WORK/play"
  need 0 "show $id" -- "$P" show "$id" --json
  need 0 "start $id" -- "$P" start "$id" --json
  session="$(json "d['session']")"; workspace="$(json "d['workspace']")"
  cd "$workspace"
  need 1 "first check fails" -- "$P" check --json
  need 0 "status without docker" -- "$P" status --json
  need 0 "hint" -- "$P" hint --json
  git apply "$ROOT/examples/$id/solution/reference.patch"
  need 0 "check passes after reference patch" -- "$P" check --json
  need 0 "history available" -- "$P" history --json
  [ "$(json "d['availability']")" = "available" ] || { echo "FAIL: history not available"; exit 1; }
  need 0 "submit" -- "$P" submit --json
  [ "$(json "d['checks']['passed']")" = "True" ] || { echo "FAIL: submitted checks not passed"; exit 1; }
  need 0 "report" -- "$P" report --json
  need 2 "hint after submit is rejected" -- "$P" hint --json
  need 0 "sessions lists it" -- "$P" sessions --json
done

say "reset restores a workspace"
cd "$WORK/play"
need 0 "start for reset" -- "$P" start pagination-last-page --json
workspace="$(json "d['workspace']")"; cd "$workspace"
echo "scratch" > src/catalog/scratch.py
need 0 "reset --yes" -- "$P" reset --yes --json
[ ! -e src/catalog/scratch.py ] || { echo "FAIL: reset left scratch file"; exit 1; }

say "authoring starters validate"
mkdir -p "$WORK/author" && cd "$WORK/author"
for combo in "debug python" "feature python" "debug typescript" "feature typescript"; do
  set -- $combo
  need 0 "new $1 $2" -- "$P" new "starter-$1-$2" --type "$1" --lang "$2" --json
  need 0 "validate starter-$1-$2" -- "$P" validate "starter-$1-$2" --json
done

say "pack install needs consent, then starts"
mkdir -p "$WORK/pack" && cd "$WORK/pack"
cp -R "$ROOT/examples/cache-expiry" . && rm -f cache-expiry/verification.json
printf 'spec_version: "0.1"\nname: rc-pack\nversion: 0.1.0\ndescription: release check\nchallenges: [cache-expiry]\n' > pack.yaml
git init -q && git add -A && git -c user.name=rc -c user.email=rc@example.test commit -qm pack
cd "$WORK/play"
mkdir -p "$WORK/fakehome"
need 0 "pack add" -- env HOME="$WORK/fakehome" "$P" pack add "$WORK/pack" --json
need 2 "start without consent is refused" -- env HOME="$WORK/fakehome" "$P" start rc-pack:cache-expiry --json
[ "$(json "d['error']['kind']")" = "consent_required" ] || { echo "FAIL: expected consent_required"; exit 1; }
need 0 "start with --yes" -- env HOME="$WORK/fakehome" "$P" start rc-pack:cache-expiry --yes --json
need 0 "pack list" -- env HOME="$WORK/fakehome" "$P" pack list --json
need 0 "pack remove" -- env HOME="$WORK/fakehome" "$P" pack remove rc-pack --yes --json

say "all release-candidate checks passed"
