---
id: patchground-web
type: module-design
status: active
title: Patchground public website
parent: patchground-architecture
implements: [patchground-contract-security]
---

## Responsibility

The public homepage presents the CLI as the product: open-source, local-first practice on real
codebases, as the alternative to algorithm-puzzle platforms for practical interviews and day-to-day
engineering. Its order is fixed: what it is and the verified-outcomes moment (hero, then a stats
strip); how it helps you practise (how a session works; the skills you practise as a bento grid
that also says who it is for; the annotated verified-outcomes report); why it exists, as the
Compare section (public statements from industry, a comparison with named practice platforms, the
three principles); the challenge catalog with its packs; installation; and last the
invitation to publish a pack or contribute. Authoring and community support the
product; they never lead. The annotated report mirrors the sections of `patchground-report` and
states facts, never judgements such as "weakened".

The hero is a layered scene: an editor window showing the fix as a diff behind the animated
terminal, with two floating facts (checks run in Docker, Git state untouched), over a CSS-only
glow, grid and guide lines. Below it a stats strip is generated from the catalog (counts of challenges,
languages, kinds of work and timeboxed hours) so it can never go stale. Catalog rows carry a
language/type tile and a three-segment difficulty bar. Everything is inline SVG or CSS; no images.

The look is dark and terminal-native around the orange patch, set in self-hosted Geist Sans and
Geist Mono. Its components follow Watermelon UI's layered bento surfaces and Cult UI's texture
card, border beam and background guides, ported to `.astro` + Tailwind rather than installed.
Motion is CSS: a finite hero reveal, scroll-driven entrances where the browser supports them, a
border beam that sweeps three times (and loops only while hovered), and hover states. Nothing
moves forever on its own.

The brand is a geometric mark: a square with its missing corner set back in ("the patch"). It is
inline SVG in every page header and footer, and the same shape is the favicon. Illustrations are
decorative inline SVG (`aria-hidden`) in the same flat style, with colours from the CSS palette.

The page states only what the CLI does today. Install is from PyPI
(`uv tool install patchground`, curated challenges bundled). Pinned pack installation by source is
implemented; registry-name installation and the publish helper are planned. The hero terminal and the annotated report are labelled
illustrations; examples
drafted with an agent are marked AI-generated; the CLI has no built-in AI in this release, so the
page never promises one; difficulty is "not yet human-rated". No fabricated
users, metrics, testimonials or results.

The installation section also offers an optional guide skill for the visitor's own AI assistant.
A visible, copyable prompt links to the repository skill and asks the assistant to get permission
before installing or changing files, and not solve the challenge unless asked. Skill and installation
links remain usable without JavaScript. This path supplements the manual CLI setup, not built-in AI;
the page states that the external assistant's permissions and data-sharing settings still apply.

Quotes in the Compare section are public statements, never testimonials: verbatim, with an
ellipsis marking every cut, attributed with the role the person held at the time, dated, linked to
the source, and labelled as not endorsing Patchground. The platform comparison states only facts
taken from each vendor's public pages, lists those pages, and carries the date they were checked;
it names alternatives worth using rather than disparaging them. Quotes, rows and sources live in
`src/lib/compare.mjs` so they are reviewed as data, and the tests require a source and date for each.

## Boundary

`web/` is an Astro project independent of the Python package. Astro, Tailwind CSS and the Geist
font packages are build-time dependencies (locked in `package-lock.json`); the output has no
runtime dependencies: static HTML/CSS, bundled font files and small progressive-enhancement
JavaScript (facet filtering, search, pack sorting, copy-to-clipboard, a pointer spotlight). No
React or other client framework. Everything is readable and navigable without JavaScript. No
remote fonts, scripts, images, analytics or browser storage. The build output is only the two
pages, `catalog.json`, the favicon and hashed CSS/JS/font assets; it never publishes sources or
tests.
`patchground-architecture` owns the public-site data boundary; `patchground-contract-security`
owns the privacy constraints.

## Catalog generation

The catalog section, the packs section, the stats strip, `catalog.json` and `status.html` are
rendered at build time by `src/lib/catalog.mjs` and the Astro pages from two inputs: `examples/*/challenge.yaml` (the built-in pack) and
`registry/index.json` / `status.json` (community packs verified by `patchground-registry`). Those
are the only places the site touches challenge data. Cards show a pack chip and a *built-in* or
*verified · date* badge; a *community* facet, search over title/summary/tags/pack, and pack sorting
(stars, recently verified, newest, challenge count; built-in first) are client-side over the
generated HTML. With no community pack the sections render an explicit empty state. A *Publish
your pack* section describes the publish-and-appear steps and marks the CLI helpers as planned. For examples the script
reads an explicit allowlist of public fields (id, title, summary, type, languages, tags, difficulty,
timebox, provenance) and never opens `workspace/`, `checks/`, `solution/` or `debrief/`, so
hidden checks, hints and reference solutions cannot reach the page. Card links go to public
tickets. Filters are bounded facets (difficulty; type and language once more than one exists)
rather than one control per tag, so the toolbar stays usable as the collection grows; tags remain
on the cards as data for a future search. Nothing generated is committed, so the site cannot
drift from its inputs: a change to the manifests or the registry index appears on the next build.
`PATCHGROUND_SITE_DATA` points a build at another repository root (used by the tests). When packs exist,
the generator reads their indexes with the same HTML/JSON contract. Registry data is untrusted:
every value is HTML-escaped by Astro, links must be plain `https://` URLs (anything else falls back to the
status page or plain text) and host counts are coerced to non-negative integers.

## Interaction and accessibility

Filters are native buttons with pressed state and an announced live count. Copy uses the visible
command or agent-prompt block, reports success only after the clipboard resolves, offers manual copying on
rejection, and hides itself when the clipboard is unavailable. A type scale with an 11px floor,
visible focus, a skip link, live regions and reduced-motion styling apply throughout; the hero
terminal reveal is finite and shows all lines at once under `prefers-reduced-motion`, which also
switches off every other animation. Layouts hold from 320px up with no horizontal scrolling.
Report illustration values stack beneath their labels on narrow screens rather than forcing fixed
columns wider than the viewport. A test-only Playwright smoke checks the real clipboard round trip,
keyboard navigation, responsive widths, and the no-JavaScript/manual-copy paths; it ships no browser
runtime dependency to visitors.
