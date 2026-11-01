import assert from "node:assert/strict";
import { readFile, readdir, stat } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import test from "node:test";
import { build, httpsUrl, loadCatalog, readPublicMetadata, renderCatalog, renderPacks, renderStatus } from "./catalog.mjs";

const root = new URL("../../", import.meta.url);
const publicRoot = new URL("../public/", import.meta.url);
const html = await readFile(new URL("index.html", publicRoot), "utf8");
const script = await readFile(new URL("main.js", publicRoot), "utf8");
const css = await readFile(new URL("styles.css", publicRoot), "utf8");
const matches = (pattern) => [...html.matchAll(pattern)];
const section = (id) => html.indexOf(`id="${id}"`);

function element(dataset = {}, textContent = "") {
  return {
    dataset, textContent, hidden: false, disabled: false, attributes: {}, listeners: {},
    setAttribute(key, value) { this.attributes[key] = value; },
    addEventListener(event, listener) { this.listeners[event] = listener; },
  };
}

function browser(clipboard) {
  const filters = ["all", "beginner", "intermediate", "community"].map((filter) => element({ filter }));
  const cards = [
    ["beginner debug python built-in", "last page pagination off-by-one patchground-examples"],
    ["intermediate debug python community", "cache ttl time demo-pack"],
    ["intermediate debug python built-in", "duplicate charges retries patchground-examples"],
  ].map(([facets, search]) => element({ facets, search }));
  const label = { hidden: true };
  const searchBox = { ...element(), value: "", closest: () => label };
  const elements = {
    ".filters": element(), "#catalog-count": element({ summary: "3 challenges in 2 packs" }, "3 challenges in 2 packs"),
    "#copy-command": element(), "#install-command": element({}, "git clone x\nuv tool install .\n"), "#copy-status": element(),
    "#catalog-search": searchBox, "#catalog-empty": element(), "#pack-grid": null, "#pack-sort": null,
  };
  elements[".filters"].hidden = elements["#copy-command"].hidden = true;
  vm.runInNewContext(script, {
    navigator: { clipboard },
    document: {
      querySelectorAll: (selector) => selector === "[data-filter]" ? filters : cards,
      querySelector: (selector) => elements[selector],
    },
  });
  return { filters, cards, elements, searchBox, label };
}

// --- Page structure and honesty -------------------------------------------------------------

test("all internal anchors exist, IDs are unique, one h1, skip link present", () => {
  const ids = matches(/\bid="([^"]+)"/g).map((match) => match[1]);
  assert.equal(ids.length, new Set(ids).size);
  for (const [, id] of matches(/href="#([^"]+)"/g)) assert.ok(ids.includes(id), id);
  assert.equal(matches(/<h1\b/g).length, 1);
  assert.match(html, /<html lang="en">/);
  assert.match(html, /class="skip-link" href="#main"/);
});

test("the CLI and real-world practice lead; contribution comes last", () => {
  const hero = html.match(/<section class="hero container"[\s\S]*?<\/section>/)[0];
  assert.match(hero, /href="#install">Get Patchground/);
  assert.match(hero, /pgnd start[\s\S]*pgnd check[\s\S]*pgnd submit/);
  assert.match(hero, /Verified outcomes/);
  assert.doesNotMatch(hero, /pgnd new|Create a challenge/);
  assert.ok(section("top") < section("how"));
  assert.ok(section("how") < section("practice"));
  assert.ok(section("practice") < section("outcomes"));
  assert.ok(section("outcomes") < section("who"));
  assert.ok(section("who") < section("why"));
  assert.ok(section("why") < section("challenges"));
  assert.ok(section("challenges") < section("packs"));
  assert.ok(section("packs") < section("install"));
  assert.ok(section("install") < section("publish"));
  assert.ok(section("publish") < section("community"));
});

test("claims stay within what the CLI does today", () => {
  assert.doesNotMatch(html, /uv tool install patchground|pip install patchground/);
  // Future CLI commands may only appear as explicitly planned, never as instructions.
  for (const m of html.matchAll(/pgnd pack (publish|add)/g)) assert.match(html.slice(Math.max(0, m.index - 200), m.index), /Planned/, m[0]);
  assert.match(html, /uv tool install git\+https:\/\/github\.com\/franndeli\/patchground/);
  assert.match(html, /pgnd list --builtin/);
  assert.match(html, /Installing packs by name from the CLI is planned/);
  assert.match(html, /Planned: <code>pgnd pack publish<\/code>/);
  assert.match(html, /No pull request/);
  assert.match(html, /not yet human-rated/);
  assert.match(html, /class="window-tag">illustration/);
  // AI coaching is deferred from this release: the page must not promise an in-CLI AI preview.
  assert.doesNotMatch(html, /see exactly what would be sent/);
  assert.match(html, /class="report-sheet" aria-label="[^"]*\(illustration\)"/);
  // The report states structural facts about tests; it never judges them "weakened".
  assert.doesNotMatch(html.match(/<div class="report-sheet"[\s\S]*?<\/div>\s*<ol/)[0], /weakened/);
  assert.doesNotMatch(html + css + script, /\/Users\/|\/home\/|sk-[A-Za-z0-9]{20}|checks\/hidden|reference\.patch/);
  assert.doesNotMatch(html, /<(?:script|link|img|iframe)[^>]+(?:src|href)="https?:/i);
  assert.doesNotMatch(css, /@import|url\(["']?https?:/i);
  assert.doesNotMatch(script, /\b(?:fetch|XMLHttpRequest|localStorage|sessionStorage|eval)\s*[.(]/);
});

test("the brand is the geometric patch mark, decorative and identical on every page", async () => {
  const status = await readFile(new URL("status.html", publicRoot), "utf8");
  const favicon = await readFile(new URL("favicon.svg", publicRoot), "utf8");
  const mark = /<a class="brand"[^>]*><svg class="brand-logo" viewBox="0 0 64 64" aria-hidden="true">/g;
  assert.equal(html.match(mark).length, 2);
  assert.equal(status.match(mark).length, 1);
  assert.doesNotMatch(html + status, /&gt;_|brand-mark/);
  assert.match(favicon, /^<svg xmlns="http:\/\/www\.w3\.org\/2000\/svg"/);
  for (const svg of html.match(/<svg class="art"[^>]*>/g)) assert.match(svg, /aria-hidden="true"/);
});

test("every local asset and repository link resolves to an existing file", async () => {
  for (const [, path] of matches(/(?:href|src)="\.\/([^"]+)"/g)) {
    assert.ok((await stat(new URL(path, publicRoot))).isFile(), path);
  }
  for (const [, path] of matches(/https:\/\/github\.com\/franndeli\/patchground\/blob\/main\/([^"#]+)/g)) {
    assert.ok((await stat(new URL(path, root))).isFile(), path);
  }
});

test("no font size below the 11px floor; reduced motion and focus styles exist", () => {
  for (const [, px] of css.matchAll(/font(?:-size)?:\s*(\d+)px/g)) assert.ok(Number(px) >= 11, `${px}px`);
  for (const [, px] of css.matchAll(/font:\s*[^;]*?(\d+)px\/[\d.]+/g)) assert.ok(Number(px) >= 11, `${px}px`);
  assert.equal(css.match(/--fs-0:\s*(\d+)px/)[1], "11");
  assert.match(css, /prefers-reduced-motion: reduce/);
  assert.match(css, /:focus-visible/);
  assert.match(css, /\.terminal-lines li \{ opacity: 1; animation: none; \}/);
});

test("no-JavaScript page shows every challenge; enhancement controls start hidden", () => {
  assert.match(html, /class="filters"[^>]+ hidden/);
  assert.match(html, /id="copy-command"[^>]+ hidden/);
  for (const [card] of matches(/<article class="challenge-card"[^>]+>/g)) assert.doesNotMatch(card, /\bhidden\b/);
});

// --- Generated catalog -----------------------------------------------------------------------

test("catalog HTML, JSON and status page are generated from manifests + registry and up to date", async () => {
  const { challenges, packs, stale } = await build({ check: true });
  assert.equal(stale, false);
  const dirs = (await readdir(new URL("examples/", root), { withFileTypes: true })).filter((d) => d.isDirectory());
  const registry = JSON.parse(await readFile(new URL("registry/index.json", root), "utf8"));
  assert.equal(packs.length, 1 + registry.packs.length);
  assert.equal(packs[0].kind, "built-in");
  const json = JSON.parse(await readFile(new URL("catalog.json", publicRoot), "utf8"));
  const expectedIds = [...dirs.map((d) => d.name), ...registry.packs.flatMap((p) => p.challenges.map((c) => c.id))].sort();
  assert.deepEqual(json.challenges.map((c) => c.id).sort(), expectedIds);
  for (const [, path] of (await readFile(new URL("status.html", publicRoot), "utf8")).matchAll(/href="\.\/([^"#]+)"/g)) {
    assert.ok((await stat(new URL(path, publicRoot))).isFile(), path);
  }
  const entries = challenges;
  for (const entry of entries) {
    assert.ok(html.includes(`data-challenge="${entry.id}"`), entry.id);
    assert.ok(html.includes(`${entry.timebox_minutes} MIN`), entry.id);
    assert.ok(html.includes(`examples/${entry.id}/TICKET.md`), entry.id);
    if (entry.provenance === "generated") assert.ok(html.includes("AI-generated"), entry.id);
  }
});

test("the metadata reader publishes only allowlisted fields and handles quotes and folds", () => {
  const meta = readPublicMetadata([
    'id: demo', 'title: Returns "page out of range"', 'summary: >-', '  First line', '  second line.',
    'tags: [a, "b"]', 'difficulty: beginner', 'timebox_minutes: 20', 'solution: solution/reference.patch',
    'checks:', '  hidden: checks/hidden', 'hints:', '  - secret hint',
  ].join("\n"));
  assert.equal(meta.title, 'Returns "page out of range"');
  assert.equal(meta.summary, "First line second line.");
  assert.deepEqual(meta.tags, ["a", "b"]);
  assert.equal(meta.timebox_minutes, 20);
  assert.equal(meta.solution, undefined);
  assert.equal(meta.checks, undefined);
  assert.equal(meta.hints, undefined);
});

const fixture = () => {
  const builtIn = { name: "patchground-examples", kind: "built-in", description: "d", homepage: "https://example.test", challenges: [
    { id: "a", title: "<b>x</b>", summary: "s", type: "debug", languages: ["python"], tags: ["t1", "t2", "t3"], difficulty: "beginner", timebox_minutes: 10, provenance: "handmade", ticket: "https://example.test/a", pack: "patchground-examples" },
  ] };
  const community = { name: "demo", kind: "community", description: "<i>c</i>", homepage: "https://example.test/demo", stars: 42, forks: 3, verified_at: "2026-10-31T10:00:00+00:00", first_seen: "2026-10-01T00:00:00+00:00", challenges: [
    { id: "b", title: "y", summary: "s", type: "feature", languages: ["go"], tags: ["t4", "t5"], difficulty: "advanced", timebox_minutes: 60, provenance: "generated", ticket: "https://example.test/b", pack: "demo" },
  ] };
  return { packs: [builtIn, community], challenges: [...builtIn.challenges, ...community.challenges] };
};

test("filters are bounded facets (plus community when present), not one button per tag, and escape HTML", () => {
  const out = renderCatalog(fixture());
  const buttons = [...out.matchAll(/data-filter="([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(buttons, ["all", "beginner", "advanced", "debug", "feature", "python", "go", "community"]);
  assert.ok(out.includes("&lt;b&gt;x&lt;/b&gt;"));
  assert.ok(!out.includes("<b>x</b>"));
  assert.ok(!out.includes('data-filter="t1"'));
  assert.match(out, /badge-verified[^>]*>verified · 2026-10-31</);
  assert.match(out, /badge-builtin">built-in</);
  assert.match(out, /data-search="[^"]*demo[^"]*"/);
});

test("pack cards carry sort keys, host stats and an empty state when no community pack exists", () => {
  const withCommunity = renderPacks(fixture().packs);
  assert.match(withCommunity, /data-kind="community" data-stars="42"/);
  assert.match(withCommunity, /★ 42/);
  assert.ok(withCommunity.includes("&lt;i&gt;c&lt;/i&gt;"));
  assert.doesNotMatch(withCommunity, /packs-empty/);
  const builtInOnly = renderPacks([fixture().packs[0]]);
  assert.match(builtInOnly, /packs-empty/);
  assert.match(builtInOnly, /1 pack · 0 community/);
});

test("untrusted community links must be plain https", () => {
  assert.equal(httpsUrl("https://github.com/x/pack"), "https://github.com/x/pack");
  for (const bad of ["javascript:alert(1)", "http://x", "https://x\" onmouseover=\"y", "data:text/html,x", 42, null]) {
    assert.equal(httpsUrl(bad), null, String(bad));
  }
  const out = renderStatus({ seen: [{ source: "javascript:alert(1)", result: "failed" }] }, []);
  assert.doesNotMatch(out, /href="javascript:/);
});

test("status page lists every seen source with its failing step and never a runner path", () => {
  const out = renderStatus({ generated_at: "2026-10-31T10:00:00+00:00", seen: [
    { source: "https://github.com/x/good.git", result: "verified", checked_at: "2026-10-31T10:00:00+00:00", detail: "1 challenges", name: "good" },
    { source: "https://github.com/x/bad.git", result: "failed", failed_step: "broken_fails", failing_challenge: "c1", checked_at: "2026-10-31T10:00:00+00:00", detail: "pgnd validate failed <script>" },
  ] }, fixture().packs);
  assert.match(out, /status-verified/);
  assert.match(out, /status-failed[\s\S]*<code>broken_fails<\/code>/);
  assert.ok(out.includes("&lt;script&gt;"));
  assert.match(out, /Verified packs: <strong>1<\/strong>/);
  assert.doesNotMatch(out, /\/Users\/|\/home\/|\/tmp\//);
  const empty = renderStatus({ seen: [] }, []);
  assert.match(empty, /Nothing seen yet/);
  assert.match(empty, /never \(no registry run yet\)/);
});

test("the catalog is sorted beginner-first across packs", async () => {
  const { challenges } = await loadCatalog();
  const order = { beginner: 0, intermediate: 1, advanced: 2 };
  for (let i = 1; i < challenges.length; i++) assert.ok(order[challenges[i - 1].difficulty] <= order[challenges[i].difficulty]);
});

// --- Behaviour -----------------------------------------------------------------------------

test("facets and search combine; the empty note appears for zero matches; All + empty query restores the summary", () => {
  const { filters, cards, elements, searchBox, label } = browser();
  assert.equal(elements[".filters"].hidden, false);
  assert.equal(label.hidden, false);
  filters[1].listeners.click();
  assert.deepEqual(cards.map((c) => c.hidden), [false, true, true]);
  assert.equal(elements["#catalog-count"].textContent, "1 challenge · beginner");
  filters[3].listeners.click();
  assert.deepEqual(cards.map((c) => c.hidden), [true, false, true]);
  assert.equal(elements["#catalog-count"].textContent, "1 challenge · community");
  filters[0].listeners.click();
  searchBox.value = "  Cache ";
  searchBox.listeners.input();
  assert.deepEqual(cards.map((c) => c.hidden), [true, false, true]);
  assert.equal(elements["#catalog-count"].textContent, "1 challenge · “cache”");
  assert.equal(elements["#catalog-empty"].hidden, true);
  searchBox.value = "nothing-here";
  searchBox.listeners.input();
  assert.ok(cards.every((c) => c.hidden));
  assert.equal(elements["#catalog-empty"].hidden, false);
  searchBox.value = "";
  searchBox.listeners.input();
  assert.ok(cards.every((c) => !c.hidden));
  assert.equal(elements["#catalog-count"].textContent, "3 challenges in 2 packs");
  assert.equal(filters.filter((b) => b.attributes["aria-pressed"] === "true").length, 1);
});

test("copy uses the exact visible command block and reports only after the clipboard resolves", async () => {
  let copied;
  let finish;
  const { elements } = browser({ writeText(text) { copied = text; return new Promise((resolve) => { finish = resolve; }); } });
  const button = elements["#copy-command"];
  assert.equal(button.hidden, false);
  const pending = button.listeners.click();
  assert.equal(button.disabled, true);
  assert.equal(elements["#copy-status"].textContent, "");
  assert.equal(copied, "git clone x\nuv tool install .");
  finish();
  await pending;
  assert.match(elements["#copy-status"].textContent, /^Copied\./);
  assert.equal(button.disabled, false);
});

test("clipboard rejection offers manual copying; unavailable clipboard hides the control", async () => {
  const rejected = browser({ writeText: async () => { throw new Error("denied"); } });
  await rejected.elements["#copy-command"].listeners.click();
  assert.match(rejected.elements["#copy-status"].textContent, /copy them manually/);
  assert.equal(rejected.elements["#copy-command"].disabled, false);
  const none = browser();
  assert.equal(none.elements["#copy-command"].hidden, true);
});

test("build refuses a stale catalog and ships exactly the allowlisted public files", async () => {
  execFileSync(process.execPath, [fileURLToPath(new URL("build.mjs", import.meta.url))]);
  const dist = new URL("../dist/", import.meta.url);
  assert.deepEqual((await readdir(dist)).sort(), ["catalog.json", "favicon.svg", "index.html", "main.js", "status.html", "styles.css"]);
  for (const name of await readdir(dist)) {
    assert.deepEqual(await readFile(new URL(name, dist)), await readFile(new URL(name, publicRoot)));
  }
});
