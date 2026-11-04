// Site tests. `npm test` runs `astro build` first; these tests read the real output in dist/ and
// build two fixture repositories (community packs, empty registry) into temporary directories.

import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, readdir, rm, stat, writeFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import test, { after } from "node:test";
import { httpsUrl, loadCatalog, readPublicMetadata } from "../src/lib/catalog.mjs";
import { CHECKED_ON, PLATFORMS, QUOTES, ROWS } from "../src/lib/compare.mjs";

const root = new URL("../../", import.meta.url);
const web = new URL("../", import.meta.url);
const dist = new URL("dist/", web);
const html = await readFile(new URL("index.html", dist), "utf8");
const statusHtml = await readFile(new URL("status.html", dist), "utf8");
const script = await readFile(new URL("src/scripts/enhance.js", web), "utf8");
const assetNames = await readdir(new URL("_astro/", dist));
const css = (await Promise.all(assetNames.filter((n) => n.endsWith(".css")).map((n) => readFile(new URL(`_astro/${n}`, dist), "utf8")))).join("\n");
const matches = (source, pattern) => [...source.matchAll(pattern)];
const section = (id) => html.indexOf(`id="${id}"`);
const text = (source) => source.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

// --- Fixture builds --------------------------------------------------------------------------

const scratch = await mkdtemp(join(tmpdir(), "pg-site-"));
after(() => rm(scratch, { recursive: true, force: true }));

async function buildFixture(name, { index, status }) {
  const repo = join(scratch, name);
  await mkdir(join(repo, "examples", "demo-bug"), { recursive: true });
  await mkdir(join(repo, "registry"), { recursive: true });
  await writeFile(join(repo, "examples", "demo-bug", "challenge.yaml"), [
    "id: demo-bug", "title: <b>x</b>", "summary: s", "type: debug", "languages: [python]", "tags: [t1, t2]",
    "difficulty: beginner", "timebox_minutes: 10", "provenance: handmade", "solution: solution/reference.patch",
    "checks:", "  hidden: checks/hidden",
  ].join("\n"));
  await writeFile(join(repo, "registry", "index.json"), JSON.stringify(index));
  await writeFile(join(repo, "registry", "status.json"), JSON.stringify(status));
  const out = join(scratch, `${name}-dist`);
  execFileSync(process.execPath, [fileURLToPath(new URL("node_modules/astro/bin/astro.mjs", web)), "build", "--outDir", out], {
    cwd: fileURLToPath(web), env: { ...process.env, PATCHGROUND_SITE_DATA: repo }, stdio: "pipe",
  });
  return {
    index: await readFile(join(out, "index.html"), "utf8"),
    status: await readFile(join(out, "status.html"), "utf8"),
    json: JSON.parse(await readFile(join(out, "catalog.json"), "utf8")),
  };
}

const community = await buildFixture("community", {
  index: { packs: [{
    name: "demo", description: "<i>c</i>", homepage: "https://example.test/demo", source: "javascript:alert(1)", stars: 42, forks: -3,
    verified_at: "2026-10-31T10:00:00+00:00", first_seen: "2026-10-01T00:00:00+00:00",
    challenges: [{ id: "b", title: "y", summary: "s", type: "feature", languages: ["go"], tags: ["t4"], difficulty: "advanced", timebox_minutes: 60, provenance: "generated", solution: "leak" }],
    tickets: { b: "javascript:alert(2)" },
  }] },
  status: { generated_at: "2026-10-31T10:00:00+00:00", seen: [
    { source: "https://github.com/x/good.git", result: "verified", checked_at: "2026-10-31T10:00:00+00:00", detail: "1 challenges", name: "good" },
    { source: "https://github.com/x/bad.git", result: "failed", failed_step: "broken_fails", failing_challenge: "c1", checked_at: "2026-10-31T10:00:00+00:00", detail: "pgnd validate failed <script>" },
    { source: "javascript:alert(3)", result: "failed" },
  ] },
});
const empty = await buildFixture("empty", { index: { packs: [] }, status: { generated_at: "1970-01-01T00:00:00+00:00", seen: [] } });

// --- Page structure and honesty --------------------------------------------------------------

test("all internal anchors exist, IDs are unique, one h1, skip link present", () => {
  for (const page of [html, statusHtml]) {
    const ids = matches(page, /\bid="([^"]+)"/g).map((m) => m[1]);
    assert.equal(ids.length, new Set(ids).size);
    for (const [, id] of matches(page, /href="#([^"]+)"/g)) assert.ok(ids.includes(id), id);
    assert.equal(matches(page, /<h1\b/g).length, 1);
    assert.ok(/<html lang="en">/.test(page), String(/<html lang="en">/));
    assert.ok(/class="skip-link[^"]*" href="#main"/.test(page), String(/class="skip-link[^"]*" href="#main"/));
  }
});

test("back-to-top links target the top of the document, not the sticky header", () => {
  // A sticky element always counts as in view, so linking to it scrolls almost nowhere.
  for (const page of [html, statusHtml]) {
    assert.ok(/<body[^>]* id="top"/.test(page), "id=top belongs on <body>");
    assert.ok(!/<header[^>]* id="top"/.test(page), "the sticky header must not be the #top target");
  }
});

test("the CLI and real-world practice lead; contribution comes last", () => {
  const hero = html.match(/<section class="hero[\s\S]*?<\/section>/)[0];
  assert.ok(/href="#install">Get Patchground/.test(hero), String(/href="#install">Get Patchground/));
  assert.ok(/pgnd start[\s\S]*pgnd check[\s\S]*pgnd submit/.test(hero), String(/pgnd start[\s\S]*pgnd check[\s\S]*pgnd submit/));
  assert.ok(/Verified outcomes/.test(hero), String(/Verified outcomes/));
  assert.ok(!/pgnd new|Create a challenge/.test(hero), String(/pgnd new|Create a challenge/));
  const order = ["top", "how", "practice", "who", "outcomes", "compare", "challenges", "packs", "install", "publish", "community"];
  for (let i = 1; i < order.length; i++) assert.ok(section(order[i - 1]) < section(order[i]), `${order[i - 1]} before ${order[i]}`);
});

test("claims stay within what the CLI does today", () => {
  const page = text(html);
  for (const m of page.matchAll(/pgnd pack (publish|add)/g)) assert.match(page.slice(Math.max(0, m.index - 200), m.index), /Planned/, m[0]);
  assert.ok(/uv tool install patchground\b/.test(html), String(/uv tool install patchground\b/));
  assert.ok(!/A PyPI package will follow/.test(page), "the package is published");
  assert.ok(/Installing packs by name from the CLI is planned/.test(page), String(/Installing packs by name from the CLI is planned/));
  assert.ok(/No pull request/.test(page), String(/No pull request/));
  assert.ok(/not yet human-rated/.test(page), String(/not yet human-rated/));
  assert.ok(/no built-in AI/.test(page), String(/no built-in AI/));
  assert.ok(/class="window-tag">illustration/.test(html), String(/class="window-tag">illustration/));
  assert.ok(/class="report-sheet[^"]*" aria-label="[^"]*\(illustration\)"/.test(html), String(/class="report-sheet[^"]*" aria-label="[^"]*\(illustration\)"/));
  const report = html.match(/class="report-sheet[\s\S]*?<\/footer>/)[0];
  assert.ok(!/weakened/.test(report), String(/weakened/));
  assert.ok(!/\/Users\/|\/home\/|sk-[A-Za-z0-9]{20}|checks\/hidden|reference\.patch/.test(html + statusHtml + css + script), String(/\/Users\/|\/home\/|sk-[A-Za-z0-9]{20}|checks\/hidden|reference\.patch/));
});

test("the install section offers an optional agent guide with a visible, consent-aware prompt", () => {
  const install = html.match(/<section[^>]*id="install"[\s\S]*?<\/section>/)[0];
  const prompt = install.match(/<p[^>]*id="agent-prompt"[^>]*>([^<]+)<\/p>/)[1];
  assert.ok(install.indexOf('id="install-command"') < install.indexOf('id="agent-prompt"'));
  assert.match(prompt, /Read https:\/\/github\.com\/franndeli\/patchground\/blob\/main\/skills\/patchground\/SKILL\.md/);
  assert.match(prompt, /Ask before installing anything or changing files/);
  assert.match(prompt, /Do not solve the challenge unless I ask/);
  assert.match(install, /href="[^"]*skills\/patchground\/SKILL\.md">View skill/);
  assert.match(install, /href="[^"]*README\.md#use-your-ai-assistant-as-a-guide">Install instructions/);
  assert.match(install, /id="copy-agent-prompt"[^>]* hidden/);
  assert.match(install, /id="agent-copy-status"[^>]*role="status"[^>]*aria-live="polite"/);
  assert.match(text(install), /no built-in AI or Patchground API key/);
  assert.match(text(install), /permissions and data-sharing settings still apply/);
});

test("nothing is loaded from another origin and scripts use no network or storage", () => {
  for (const page of [html, statusHtml]) assert.ok(!/<(?:script|link|img|iframe|source)[^>]+(?:src|href)="(?:https?:)?\/\//i.test(page), String(/<(?:script|link|img|iframe|source)[^>]+(?:src|href)="(?:https?:)?\/\//i));
  assert.ok(!/url\(["']?(?:https?:)?\/\//i.test(css), "CSS loads a remote url()");
  assert.ok(!/\b(?:fetch|XMLHttpRequest|localStorage|sessionStorage|eval)\s*[.(]/.test(script), String(/\b(?:fetch|XMLHttpRequest|localStorage|sessionStorage|eval)\s*[.(]/));
});

test("every local asset and repository link resolves to an existing file", async () => {
  for (const page of [html, statusHtml]) {
    for (const [, path] of matches(page, /(?:href|src)="(?:\.\/|\/)((?:_astro\/)?[^"#/][^"#]*)"/g)) {
      assert.ok((await stat(new URL(path, dist))).isFile(), path);
    }
    for (const [, path] of matches(page, /href="https:\/\/github\.com\/franndeli\/patchground\/blob\/main\/([^"#]+)/g)) {
      assert.ok((await stat(new URL(path, root))).isFile(), path);
    }
  }
});

test("the brand is the geometric patch mark, decorative and identical on every page", async () => {
  const favicon = await readFile(new URL("favicon.svg", dist), "utf8");
  const mark = /<a class="brand[^"]*"[^>]*><svg class="brand-logo[^"]*" viewBox="0 0 64 64" aria-hidden="true">/g;
  assert.equal(html.match(mark).length, 2);
  assert.equal(statusHtml.match(mark).length, 1);
  assert.ok(/^<svg xmlns="http:\/\/www\.w3\.org\/2000\/svg"/.test(favicon), String(/^<svg xmlns="http:\/\/www\.w3\.org\/2000\/svg"/));
  for (const svg of html.match(/<svg[^>]*>/g)) assert.match(svg, /aria-hidden="true"/, svg);
});

test("no font size below the 11px floor; reduced motion and focus styles exist", () => {
  const px = (value) => (value.endsWith("rem") ? parseFloat(value) * 16 : parseFloat(value));
  for (const [, value] of css.matchAll(/--text-[\w-]+:\s*([\d.]+(?:px|rem))/g)) assert.ok(px(value) >= 11, value);
  for (const [, value] of css.matchAll(/font-size:\s*([\d.]+(?:px|rem))/g)) assert.ok(px(value) >= 11, value);
  for (const [, value] of css.matchAll(/font-size:\s*([\d.]+)em\b/g)) assert.ok(Number(value) >= 1, `${value}em shrinks text`);
  assert.ok(/prefers-reduced-motion:\s*reduce/.test(css), "reduced-motion styles");
  assert.ok(/:focus-visible/.test(css), "focus-visible styles");
});

test("motion is finite: nothing animates forever unless the pointer is on it", () => {
  const unhovered = css.replace(/\.beam:hover:after\{[^}]*\}/g, "");
  assert.ok(!/infinite/.test(unhovered), "an animation runs forever without hover");
});

test("no-JavaScript page shows every challenge; enhancement controls start hidden", () => {
  assert.ok(/class="filters[^"]*"[^>]+ hidden/.test(html), String(/class="filters[^"]*"[^>]+ hidden/));
  assert.ok(/<label class="search[^"]*" hidden/.test(html), String(/<label class="search[^"]*" hidden/));
  assert.ok(/id="copy-command"[^>]+ hidden/.test(html), String(/id="copy-command"[^>]+ hidden/));
  for (const [card] of matches(html, /<article class="challenge-card[^>]+>/g)) assert.ok(!/\bhidden\b/.test(card), String(/\bhidden\b/));
});

test("quotes are attributed, dated, sourced and never presented as endorsements", () => {
  assert.ok(QUOTES.length >= 5);
  for (const q of QUOTES) {
    assert.ok(httpsUrl(q.source), q.who);
    assert.ok(q.who && q.role && /\d{4}/.test(q.date), q.who);
    assert.ok(html.includes(`cite="${q.source}"`), q.who);
  }
  assert.ok(/not endorsements of Patchground/.test(text(html)));
  // Cuts are marked: a quote that ends early or skips text uses an ellipsis.
  assert.ok(QUOTES.find((q) => q.who === "Max Howell").text.endsWith("…"));
});

test("quote cards use a grid, not CSS multi-column", () => {
  // Chrome repaints multi-column fragments black when a hover effect in another column composites.
  const quotes = html.match(/<figure class="quotes[\s\S]*?<\/figure>/)[0];
  assert.ok(!/\bcolumns-\d|break-inside/.test(quotes), "quotes are laid out with CSS columns");
});

test("the comparison is complete, dated and sourced for every other platform", () => {
  assert.equal(PLATFORMS.filter((p) => p.ours).length, 1);
  for (const p of PLATFORMS) {
    assert.equal(p.cells.length, ROWS.length, p.name);
    if (!p.ours) {
      assert.ok(p.sources.length > 0 && p.sources.every((s) => s.label && httpsUrl(s.url)), p.name);
      for (const s of p.sources) assert.ok(html.includes(`href="${s.url}"`), s.url);
    }
  }
  assert.ok(text(html).includes(`checked ${CHECKED_ON}`));
  assert.ok(/<a [^>]*href="#compare"/.test(html), "Compare is in the navigation");
});

// --- Catalog data ----------------------------------------------------------------------------

test("catalog HTML, JSON and stats come from the manifests and the registry", async () => {
  const { challenges, packs } = await loadCatalog(root);
  const dirs = (await readdir(new URL("examples/", root), { withFileTypes: true })).filter((d) => d.isDirectory());
  const registry = JSON.parse(await readFile(new URL("registry/index.json", root), "utf8"));
  assert.equal(packs.length, 1 + registry.packs.length);
  const json = JSON.parse(await readFile(new URL("catalog.json", dist), "utf8"));
  const expected = [...dirs.map((d) => d.name), ...registry.packs.flatMap((p) => p.challenges.map((c) => c.id))].sort();
  assert.deepEqual(json.challenges.map((c) => c.id).sort(), expected);
  for (const entry of challenges) {
    assert.ok(html.includes(`data-challenge="${entry.id}"`), entry.id);
    assert.ok(html.includes(`examples/${entry.id}/TICKET.md`), entry.id);
  }
  assert.match(text(html), new RegExp(`${challenges.length} curated challenges`));
});

test("all eight approved interview challenges ship as generated catalog entries and cards", async () => {
  const approved = [
    "config-precedence", "draft-edit-isolation", "cron-field-expansion", "invoice-monthly-summary",
    "sliding-window-rate-limit", "search-response-ordering", "webhook-retry-scheduling", "transaction-rule-evaluator",
  ];
  const json = JSON.parse(await readFile(new URL("catalog.json", dist), "utf8"));
  for (const id of approved) {
    const entries = json.challenges.filter((entry) => entry.id === id && entry.pack === "patchground-examples");
    assert.equal(entries.length, 1, `missing or duplicate approved challenge: ${id}`);
    assert.equal(entries[0].provenance, "generated", id);
    assert.ok(html.includes(`data-challenge="${id}"`), `missing card: ${id}`);
    assert.ok(html.includes(`examples/${id}/TICKET.md`), `missing ticket link: ${id}`);
    for (const privateField of ["checks", "solution", "hints", "generated_by"]) {
      assert.equal(entries[0][privateField], undefined, `${id}: private field ${privateField}`);
    }
  }
});

test("the metadata reader publishes only allowlisted fields and handles quotes and folds", () => {
  const meta = readPublicMetadata([
    "id: demo", 'title: Returns "page out of range"', "summary: >-", "  First line", "  second line.",
    'tags: [a, "b"]', "difficulty: beginner", "timebox_minutes: 20", "solution: solution/reference.patch",
    "checks:", "  hidden: checks/hidden", "hints:", "  - secret hint",
  ].join("\n"));
  assert.equal(meta.title, 'Returns "page out of range"');
  assert.equal(meta.summary, "First line second line.");
  assert.deepEqual(meta.tags, ["a", "b"]);
  assert.equal(meta.timebox_minutes, 20);
  assert.equal(meta.solution, undefined);
  assert.equal(meta.checks, undefined);
  assert.equal(meta.hints, undefined);
});

test("untrusted community links must be plain https", () => {
  assert.equal(httpsUrl("https://github.com/x/pack"), "https://github.com/x/pack");
  for (const bad of ["javascript:alert(1)", "http://x", 'https://x" onmouseover="y', "data:text/html,x", 42, null]) {
    assert.equal(httpsUrl(bad), null, String(bad));
  }
});

test("the catalog is sorted beginner-first across packs", async () => {
  const { challenges } = await loadCatalog(root);
  const order = { beginner: 0, intermediate: 1, advanced: 2 };
  for (let i = 1; i < challenges.length; i++) assert.ok(order[challenges[i - 1].difficulty] <= order[challenges[i].difficulty]);
});

test("community packs: bounded facets, escaped values, verified badges, sort keys and safe links", () => {
  const page = community.index;
  assert.deepEqual(matches(page, /data-filter="([^"]+)"/g).map((m) => m[1]), ["all", "beginner", "advanced", "debug", "feature", "python", "go", "community"]);
  // Inside quoted attribute values "<" is inert; everywhere else it must be escaped.
  const markup = page.replace(/="[^"]*"/g, '=""');
  assert.ok(markup.includes("&lt;b") && !markup.includes("<b>x</b>"));
  assert.ok(markup.includes("&lt;i") && !markup.includes("<i>c</i>"));
  assert.ok(/badge-verified[^>]*>verified · 2026-10-31</.test(page), String(/badge-verified[^>]*>verified · 2026-10-31</));
  assert.ok(/data-search="[^"]*demo[^"]*"/.test(page), String(/data-search="[^"]*demo[^"]*"/));
  assert.ok(/data-kind="community" data-stars="42"/.test(page), String(/data-kind="community" data-stars="42"/));
  assert.ok(/★ 42/.test(page), String(/★ 42/));
  assert.ok(/⑂ 0/.test(page), String(/⑂ 0/));
  assert.ok(!/class="packs-empty/.test(page), String(/class="packs-empty/));
  assert.ok(!/href="javascript:/.test(page + community.status), String(/href="javascript:/));
  assert.equal(community.json.challenges.find((c) => c.id === "b").solution, undefined);
  assert.ok(!/checks\/hidden|reference\.patch|pg-site-/.test(page + community.status), String(/checks\/hidden|reference\.patch|pg-site-/));
});

test("status page lists every seen source with its failing step; empty registries say so", () => {
  const out = community.status;
  assert.ok(/status-verified/.test(out), String(/status-verified/));
  assert.ok(/status-failed[\s\S]*<code[^>]*>broken_fails<\/code>/.test(out), String(/status-failed[\s\S]*<code[^>]*>broken_fails<\/code>/));
  assert.ok(out.includes("&lt;script&gt;"));
  assert.ok(/Verified packs: 1/.test(text(out)), String(/Verified packs: 1/));
  assert.ok(/Nothing seen yet/.test(text(empty.status)), String(/Nothing seen yet/));
  assert.ok(/never \(no registry run yet\)/.test(text(empty.status)), String(/never \(no registry run yet\)/));
  assert.ok(/class="packs-empty/.test(empty.index), String(/class="packs-empty/));
  assert.ok(/1 pack · 0 community/.test(text(empty.index)), String(/1 pack · 0 community/));
});

// --- Behaviour -------------------------------------------------------------------------------

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
    "#copy-agent-prompt": element(), "#agent-prompt": element({}, html.match(/<p[^>]*id="agent-prompt"[^>]*>([^<]+)<\/p>/)[1]), "#agent-copy-status": element(),
    "#catalog-search": searchBox, "#catalog-empty": element(), "#pack-grid": null, "#pack-sort": null,
  };
  elements[".filters"].hidden = elements["#copy-command"].hidden = elements["#copy-agent-prompt"].hidden = true;
  const all = { "[data-filter]": filters, "[data-facets]": cards, "[data-spotlight]": [] };
  vm.runInNewContext(script, {
    navigator: { clipboard },
    document: { querySelectorAll: (selector) => all[selector], querySelector: (selector) => elements[selector] },
  });
  return { filters, cards, elements, searchBox, label };
}

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
  const { elements } = browser({ writeText(value) { copied = value; return new Promise((resolve) => { finish = resolve; }); } });
  const button = elements["#copy-command"];
  assert.equal(button.hidden, false);
  const pending = button.listeners.click();
  assert.equal(button.disabled, true);
  assert.equal(elements["#copy-status"].textContent, "");
  assert.equal(copied, "git clone x\nuv tool install .");
  finish();
  await pending;
  assert.ok(/^Copied\./.test(elements["#copy-status"].textContent), String(/^Copied\./));
  assert.equal(button.disabled, false);
});

test("clipboard rejection offers manual copying; unavailable clipboard hides the control", async () => {
  const rejected = browser({ writeText: async () => { throw new Error("denied"); } });
  await rejected.elements["#copy-command"].listeners.click();
  assert.ok(/copy them manually/.test(rejected.elements["#copy-status"].textContent), String(/copy them manually/));
  assert.equal(rejected.elements["#copy-command"].disabled, false);
  const none = browser();
  assert.equal(none.elements["#copy-command"].hidden, true);
});

test("agent prompt copies independently and announces success only after the clipboard resolves", async () => {
  let copied;
  let finish;
  const { elements } = browser({ writeText(value) { copied = value; return new Promise((resolve) => { finish = resolve; }); } });
  const button = elements["#copy-agent-prompt"];
  assert.equal(button.hidden, false);
  const pending = button.listeners.click();
  assert.equal(button.disabled, true);
  assert.equal(elements["#agent-copy-status"].textContent, "");
  assert.equal(copied, elements["#agent-prompt"].textContent.trim());
  finish();
  await pending;
  assert.match(elements["#agent-copy-status"].textContent, /^Copied\. Paste into your AI assistant/);
  assert.equal(button.disabled, false);
  assert.equal(elements["#copy-status"].textContent, "");
});

test("agent clipboard failure offers manual copying and missing clipboard leaves the prompt available", async () => {
  const { elements } = browser({ writeText: async () => { throw new Error("denied"); } });
  await elements["#copy-agent-prompt"].listeners.click();
  assert.match(elements["#agent-copy-status"].textContent, /copy it manually/);
  assert.equal(elements["#copy-agent-prompt"].disabled, false);
  assert.equal(elements["#copy-status"].textContent, "");
  const none = browser();
  assert.equal(none.elements["#copy-agent-prompt"].hidden, true);
  assert.match(none.elements["#agent-prompt"].textContent, /guide me through getting started/);
});

// --- Build output ----------------------------------------------------------------------------

test("the build ships only pages, the catalog, the favicon and hashed CSS/JS/font assets", async () => {
  assert.deepEqual((await readdir(dist)).sort(), ["_astro", "catalog.json", "favicon.svg", "index.html", "status.html"]);
  for (const name of assetNames) assert.match(name, /^[\w-]+\.[\w-]+\.(?:css|js|woff2)$/, name);
});
