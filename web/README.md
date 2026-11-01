# Patchground website

The public homepage for the Patchground CLI: what it is, how it helps you practise (session flow,
skills, the verified-outcomes report, who it is for), why it exists, the challenge catalog, and
how to install it. A standalone static site—no framework, no npm dependencies, no backend. It is
not a browser runner, a hosted community platform, or a documentation site (docs stay in the repo
until a docs build exists).

## Local preview

Requirements: Node.js 22+ for checks/build, Python 3 for the preview server.

```sh
npm --prefix web run dev        # http://127.0.0.1:4173, loopback only
```

Edit `web/public/` and reload. Stop with Ctrl+C.

## The catalog is generated

`web/public/index.html` contains two marked regions (`catalog:start/end`, `packs:start/end`);
`catalog.json` and `status.html` are generated too. `scripts/catalog.mjs` produces all of them from
`examples/*/challenge.yaml` (the built-in pack) and from `registry/index.json` + `status.json`
(community packs verified by the registry workflow — see `registry/SPEC.md`). From examples it
reads **only** this allowlist of public fields:
`id, title, summary, type, languages, tags, difficulty, timebox_minutes, provenance`. The script
never opens `workspace/`, `checks/`, `solution/` or `debrief/`.

```sh
npm --prefix web run catalog    # regenerate after adding or editing a challenge
npm --prefix web run build      # refuses to build if the catalog is stale
```

Adding a challenge to `examples/` therefore adds it to the site with one command. Filters are
bounded facets (difficulty, and type/language once more than one exists), so the toolbar stays
usable as the collection grows. Tags are kept on each card as data for a future search box.
`catalog.json` is the stable interface for any later catalog page or external tooling.

Community packs flow in through `registry/index.json`, which only CI writes; the registry's
`publish` job regenerates the site in the same commit, so the two never drift. To preview the site
with community data locally, run the crawler against a test pack (see `registry/crawl.py`
`--source` and `PG_REGISTRY_ALLOW_FILE=1`), run `npm --prefix web run catalog`, and restore the
JSON files before committing.

## Verify and build

```sh
npm --prefix web run check      # syntax check of all scripts
npm --prefix web test           # 18 tests: structure, honesty, brand, assets, type floor, catalog, packs, status, behaviour, build
npm --prefix web run build      # web/dist/: index.html, status.html, styles.css, main.js, favicon.svg, catalog.json
```

`.github/workflows/web.yml` runs the same on pushes/PRs touching `web/` or any `challenge.yaml`.
It does not deploy. `web/dist/` uses relative URLs and needs no server-side routing; hosting, DNS
and production deployment are a separate, owner-approved step.

## Editorial rules (tests enforce the ones they can)

- The CLI and practising on real code lead; authoring/community comes last.
- No claim beyond what the CLI does today: install is from a checkout until a package is published;
  `pgnd pack publish` / `pack add <name>` appear only as *planned*; the hero terminal and the
  annotated report are labelled *illustration*; AI-generated examples say so; *verified* means "passed `pgnd validate` in our CI".
- No remote fonts, scripts, images, analytics or storage. Everything works without JavaScript;
  JS only adds filtering and copy-to-clipboard.
- Nothing renders below 11px. Motion is finite and disabled under `prefers-reduced-motion`.
- No personal paths, secrets, hidden-check or reference-solution contents anywhere in `web/`.

## Browser review checklist

Desktop and 320px mobile: no horizontal overflow; the hero terminal finishes revealing within ~7s
(or shows at once with reduced motion); facet filters work by keyboard with visible focus and an
announced count; copy succeeds, and denied/unavailable clipboard degrades gracefully; with scripts
disabled every challenge and link is still visible; no console errors.
