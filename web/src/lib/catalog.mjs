// Public catalog data for the site, read at build time.
//
// Sources (relative to the repository root passed in):
//   - examples/*/challenge.yaml  → the built-in pack. Only PUBLIC_FIELDS are read; workspace/,
//     checks/, solution/ and debrief/ are never opened.
//   - registry/index.json        → community packs already verified by registry/crawl.py in CI.
//   - registry/status.json       → every source the crawler saw, for the status page.
//
// Registry data is untrusted: links must be plain https URLs and counts non-negative integers.
// Astro escapes every interpolated value when it renders the pages.

import { readFile, readdir } from "node:fs/promises";
import { pathToFileURL } from "node:url";

export const REPO = "https://github.com/franndeli/patchground";
export const PUBLIC_FIELDS = ["id", "title", "summary", "type", "languages", "tags", "difficulty", "timebox_minutes", "provenance"];
export const LEVELS = ["beginner", "intermediate", "advanced"];

const LANG_TAGS = { python: "Py", typescript: "TS", javascript: "JS", go: "Go", rust: "Rs", java: "Jv" };
const unquote = (s) => (/^(["']).*\1$/.test(s) ? s.slice(1, -1) : s);
export const title = (s) => s.charAt(0).toUpperCase() + s.slice(1);
export const pad = (n) => String(n).padStart(2, "0");
export const day = (iso) => (typeof iso === "string" ? iso.slice(0, 10) : "");
export const httpsUrl = (u) => (typeof u === "string" && /^https:\/\/[^\s"'<>`\\]+$/.test(u) ? u : null);
const count = (n) => (Number.isSafeInteger(n) && n >= 0 ? n : 0);
const plural = (n, word) => `${n} ${n === 1 ? word : `${word}s`}`;

/** The repository root: `PATCHGROUND_SITE_DATA` (test fixtures) or the parent of web/. */
export function dataRoot() {
  const dir = process.env.PATCHGROUND_SITE_DATA || `${process.cwd()}/..`;
  return pathToFileURL(dir.endsWith("/") ? dir : `${dir}/`);
}

/** Minimal reader for the flat top-level scalars, inline lists and folded blocks we publish. */
export function readPublicMetadata(yaml) {
  const lines = yaml.split("\n");
  const out = {};
  for (let i = 0; i < lines.length; i++) {
    const match = lines[i].match(/^([a-z_]+):\s*(.*)$/);
    if (!match || !PUBLIC_FIELDS.includes(match[1])) continue;
    const [, key, raw] = match;
    if (raw === ">-" || raw === ">" || raw === "|") {
      const block = [];
      while (lines[i + 1]?.startsWith("  ")) block.push(lines[++i].trim());
      out[key] = block.join(" ");
    } else if (raw.startsWith("[")) {
      out[key] = raw.slice(1, raw.lastIndexOf("]")).split(",").map((s) => unquote(s.trim())).filter(Boolean);
    } else {
      out[key] = unquote(raw);
    }
  }
  if (out.timebox_minutes) out.timebox_minutes = Number(out.timebox_minutes);
  return out;
}

async function readJson(url, fallback) {
  try { return JSON.parse(await readFile(url, "utf8")); } catch { return fallback; }
}

async function loadBuiltIn(root) {
  const examples = new URL("examples/", root);
  const dirs = (await readdir(examples, { withFileTypes: true })).filter((d) => d.isDirectory()).map((d) => d.name).sort();
  const challenges = [];
  for (const name of dirs) {
    const meta = readPublicMetadata(await readFile(new URL(`${name}/challenge.yaml`, examples), "utf8"));
    if (meta.id !== name) throw new Error(`examples/${name}: manifest id "${meta.id}" does not match its folder`);
    challenges.push({ ...meta, pack: "patchground-examples", ticket: `${REPO}/blob/main/examples/${name}/TICKET.md` });
  }
  return {
    name: "patchground-examples", kind: "built-in", description: "Curated examples shipped with the CLI; validated in this repository's CI on every push.",
    source: REPO, homepage: `${REPO}/tree/main/examples`, challenges, stars: null, forks: null, verified_at: null, first_seen: null,
  };
}

async function loadCommunity(root) {
  const index = await readJson(new URL("registry/index.json", root), { packs: [] });
  return (index.packs || []).map((p) => ({
    name: p.name, kind: "community", description: p.description, version: p.version, source: httpsUrl(p.source), homepage: httpsUrl(p.homepage) || httpsUrl(p.source) || "./status.html",
    host: p.host, commit: p.commit, verified_at: p.verified_at, first_seen: p.first_seen, stars: count(p.stars), forks: count(p.forks),
    challenges: (p.challenges || []).map((c) => ({
      ...Object.fromEntries(PUBLIC_FIELDS.filter((k) => k in c).map((k) => [k, c[k]])),
      pack: p.name, ticket: httpsUrl((p.tickets || {})[c.id]) || httpsUrl(p.homepage) || httpsUrl(p.source) || "./status.html",
    })),
  }));
}

export async function loadCatalog(root = dataRoot()) {
  const packs = [await loadBuiltIn(root), ...(await loadCommunity(root))];
  const order = Object.fromEntries(LEVELS.map((level, i) => [level, i]));
  const challenges = packs.flatMap((p) => p.challenges)
    .sort((a, b) => (order[a.difficulty] ?? 9) - (order[b.difficulty] ?? 9) || a.timebox_minutes - b.timebox_minutes || a.id.localeCompare(b.id));
  return { packs, challenges };
}

export async function loadStatus(root = dataRoot()) {
  const status = await readJson(new URL("registry/status.json", root), { seen: [] });
  const seen = (status.seen || []).slice().sort((a, b) => String(a.source).localeCompare(String(b.source)));
  const generated = status.generated_at && !status.generated_at.startsWith("1970") ? day(status.generated_at) : "never (no registry run yet)";
  return { seen, generated };
}

/** Everything the catalog, packs and stats sections render, derived once from the catalog. */
export function catalogView({ packs, challenges }) {
  const byName = Object.fromEntries(packs.map((p) => [p.name, p]));
  const types = [...new Set(challenges.map((e) => e.type))];
  const languages = [...new Set(challenges.flatMap((e) => e.languages))];
  const difficulties = LEVELS.filter((d) => challenges.some((e) => e.difficulty === d));
  const communityPacks = packs.filter((p) => p.kind === "community");
  const facetsOf = (e) => [e.difficulty, e.type, ...e.languages, byName[e.pack].kind];
  // Facets stay bounded as the catalog grows; a facet with one value adds no button. Tags are
  // searched by the text box rather than rendered as filters.
  const facets = [...difficulties, ...(types.length > 1 ? types : []), ...(languages.length > 1 ? languages : []), ...(communityPacks.length ? ["community"] : [])];
  const minutes = challenges.reduce((sum, e) => sum + e.timebox_minutes, 0);

  return {
    summary: `${plural(challenges.length, "challenge")} in ${plural(packs.length, "pack")} · ${languages.map(title).join(", ")} · ${types.map(title).join(", ")}`,
    filters: [
      { id: "all", label: "All", count: challenges.length },
      ...facets.map((f) => ({ id: f, label: title(f), count: challenges.filter((e) => facetsOf(e).includes(f)).length })),
    ],
    challenges: challenges.map((e) => ({
      ...e,
      packInfo: byName[e.pack],
      facets: facetsOf(e).join(" "),
      search: [e.title, e.summary, e.tags.join(" "), e.pack].join(" ").toLowerCase(),
      langTag: e.languages.map((l) => LANG_TAGS[l] || l.slice(0, 2).toUpperCase()).join("/"),
      level: LEVELS.indexOf(e.difficulty),
      topic: `${e.languages.map(title).join(" / ")} / ${title(e.type)} · ${e.tags.join(", ")}`,
    })),
    packs: packs.map((p) => ({ ...p, types: [...new Set(p.challenges.map((c) => c.type))].map(title).join(", "), countLabel: plural(p.challenges.length, "challenge") })),
    packSummary: `${plural(packs.length, "pack")} · ${communityPacks.length} community`,
    hasCommunity: communityPacks.length > 0,
    stats: [
      { value: String(challenges.length), label: "curated challenges, validated in Docker" },
      { value: String(languages.length), label: languages.map(title).join(" and ") },
      { value: String(types.length), label: `kinds of work: ${types.join(", ")}` },
      { value: `${Math.round(minutes / 6) / 10}h`, label: "of timeboxed practice" },
      { value: "0", label: "accounts, API keys or scores" },
    ],
  };
}

/** The stable machine-readable catalog served as /catalog.json. */
export function catalogJson({ packs, challenges }) {
  return `${JSON.stringify({
    schema: "patchground-web-catalog/1",
    generated_from: ["examples/*/challenge.yaml (public fields only)", "registry/index.json"],
    fields: PUBLIC_FIELDS,
    packs: packs.map(({ challenges: list, ...p }) => ({ ...p, challenge_count: list.length })),
    challenges,
  }, null, 2)}\n`;
}
