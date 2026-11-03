# Patchground website

The public homepage for the Patchground CLI: what it is, how a session works, the skills you
practise and who it is for, the verified-outcomes report, why it exists, the challenge catalog,
installation, and publishing a pack. A static [Astro](https://astro.build) site styled with
Tailwind CSS v4 and the self-hosted Geist typeface. Astro, Tailwind and the fonts are build-time
dependencies only: the output is plain HTML, CSS, a few hundred bytes of progressive-enhancement
JavaScript and font files. No backend, no React, no remote assets. It is not a browser runner, a
hosted community platform, or a documentation site.

## Local preview

Requirements: Node.js 22.12+.

```sh
npm --prefix web ci
npm --prefix web run dev        # http://127.0.0.1:4173, loopback only, hot reload
npm --prefix web run preview    # serves the last `build` from web/dist/
```

## Layout

```
src/pages/index.astro      the homepage; composes the section components in order
src/pages/status.astro     status.html, every source the registry has seen
src/pages/catalog.json.ts  catalog.json, the stable machine-readable catalog
src/components/            one component per section (Hero, HowItWorks, Practice, Outcomes,
                           Compare, Catalog, Install, OpenSource) plus small shared pieces
src/lib/catalog.mjs        reads challenge manifests and the registry at build time
src/lib/compare.mjs        sourced public quotes and the dated platform comparison
src/scripts/enhance.js     filters, search, pack sort, copy, pointer spotlight
src/styles/global.css      theme tokens, shared surfaces and motion
```

The visual language comes from Watermelon UI (bento surfaces), Cult UI (texture card, border beam,
background guides) ported to plain `.astro` + Tailwind and CSS; nothing from those libraries is
installed.

## The catalog is built, not committed

`src/lib/catalog.mjs` reads `examples/*/challenge.yaml` (the built-in pack) and
`registry/index.json` + `status.json` (community packs verified by the registry workflow; see
`registry/SPEC.md`) every time the site builds. From examples it reads **only** this allowlist of
public fields: `id, title, summary, type, languages, tags, difficulty, timebox_minutes, provenance`.
It never opens `workspace/`, `checks/`, `solution/` or `debrief/`. Registry values are untrusted:
links must be plain `https://` URLs and counts non-negative integers; Astro escapes every value.

Adding a challenge to `examples/` therefore adds it to the site on the next build; there is
nothing to regenerate or commit. Filters are bounded facets (difficulty, and type/language once
more than one exists). `catalog.json` is the stable interface for external tooling.

To preview with other data, point the build at another repository root:
`PATCHGROUND_SITE_DATA=/path/to/root npm --prefix web run dev` (it needs `examples/` and
`registry/`). The tests use this to build fixture repositories.

## Verify and build

```sh
npm --prefix web run check      # syntax check of the plain JS modules
npm --prefix web test           # astro build, then tests on dist/ and two fixture builds
npm --prefix web exec -- playwright install chromium
npm --prefix web run test:browser # real clipboard readback, keyboard, mobile, no-script paths
npm --prefix web run build      # web/dist/: index.html, status.html, catalog.json, favicon.svg, _astro/*
```

The browser smoke uses test-only Playwright. It serves the built site on an ephemeral loopback port,
launches an isolated headless Chromium, and closes both after the run. It grants clipboard permission
only to that browser context and compares readback with the visible prompt. Set
`PLAYWRIGHT_CHANNEL=chrome` to use an already installed Chrome instead of downloading Chromium.
Clipboard rejection is simulated separately; the successful write/readback uses the real browser API.

`.github/workflows/web.yml` runs `npm ci`, static tests, and the browser smoke on pushes/PRs touching `web/`, any
`challenge.yaml` or the registry JSON. It does not deploy. Pages link to each other with relative
URLs; hashed assets live under `/_astro/`, so the site is served from a domain root
(`patchground.dev`). Hosting, DNS and production deployment are a separate, owner-approved step.

## Editorial rules (tests enforce the ones they can)

- The CLI and practising on real code lead; authoring/community comes last.
- No claim beyond what the CLI does today: install is from PyPI (`uv tool install patchground`);
  `pgnd pack publish` / `pack add <name>` appear only as *planned*; the hero terminal and the
  annotated report are labelled *illustration*; AI-generated examples say so; *verified* means
  "passed `pgnd validate` in our CI". No fabricated users, metrics or testimonials.
- Quotes are verbatim public statements with role, date and a source link, marked as not
  endorsements; comparison cells come from the vendors' public pages and carry the check date.
  Re-check `src/lib/compare.mjs` and bump `CHECKED_ON` when you touch it.
- Nothing is loaded from another origin: fonts are bundled, no analytics, no storage. Everything
  works without JavaScript; JS only adds filtering, sorting, copy-to-clipboard and the spotlight.
- Nothing renders below 11px (`text-2xs`). Motion is finite unless the pointer is on it, and off
  under `prefers-reduced-motion`.
- No personal paths, secrets, hidden-check or reference-solution contents anywhere in `web/`.

## Browser review checklist

Desktop and 375px mobile: no horizontal overflow; the hero terminal finishes revealing within ~6s
(or shows at once with reduced motion); facet filters work by keyboard with visible focus and an
announced count; copy succeeds, and denied/unavailable clipboard degrades gracefully; with scripts
disabled every challenge and link is still visible; no console errors.
