import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const dist = fileURLToPath(new URL("../dist/", import.meta.url));
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".woff2": "font/woff2", ".svg": "image/svg+xml" };
const server = createServer(async (request, response) => {
  const pathname = new URL(request.url, "http://localhost").pathname;
  const file = resolve(dist, `.${pathname === "/" ? "/index.html" : pathname}`);
  if (!file.startsWith(dist.endsWith(sep) ? dist : `${dist}${sep}`)) {
    response.writeHead(403).end();
    return;
  }
  try {
    const body = await readFile(file);
    response.writeHead(200, { "Content-Type": types[extname(file)] || "application/octet-stream" }).end(body);
  } catch {
    response.writeHead(404).end();
  }
});

await new Promise((resolve, reject) => {
  server.once("error", reject);
  server.listen(0, "127.0.0.1", resolve);
});
const url = `http://127.0.0.1:${server.address().port}/`;
let browser;
try {
  browser = await chromium.launch(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {});
  const context = await browser.newContext({ permissions: ["clipboard-read", "clipboard-write"], reducedMotion: "reduce" });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(url);
  const prompt = await page.locator("#agent-prompt").innerText();
  const button = page.locator("#copy-agent-prompt");
  await button.click();
  await page.waitForFunction(() => document.querySelector("#agent-copy-status").textContent.startsWith("Copied."));
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), prompt.trim());
  assert.equal(await button.isEnabled(), true);
  assert.equal(await page.locator("#copy-status").innerText(), "");
  console.log("PASS: real browser clipboard write/readback matches the visible agent prompt");

  const cards = page.locator(".challenge-card");
  const visibleCards = () => cards.evaluateAll((all) => all.filter((card) => !card.hidden).map((card) => card.dataset.challenge));
  const total = await cards.count();
  const pages = Math.ceil(total / 5);
  const first = await visibleCards();
  assert.equal(first.length, Math.min(5, total));
  assert.equal(await page.locator("#catalog-page").innerText(), `Page 1 of ${pages}`);
  const seen = [...first];
  for (let p = 2; p <= pages; p++) {
    await page.locator("#catalog-next").click();
    const shown = await visibleCards();
    assert.ok(shown.length > 0 && shown.length <= 5);
    seen.push(...shown);
  }
  assert.equal(new Set(seen).size, total);
  assert.equal(await page.locator("#catalog-next").isDisabled(), true);
  await page.locator('[data-filter="beginner"]').click();
  assert.equal(await page.locator("#catalog-page").innerText().then((t) => t.startsWith("Page 1 of")), true);
  await page.locator('[data-filter="all"]').click();
  console.log(`PASS: the catalog shows five per page; paging reaches all ${total} challenges; filters reset to page one`);

  await button.focus();
  await page.keyboard.press("Tab");
  assert.equal(await page.evaluate(() => document.activeElement.textContent.trim()), "View skill ↗");
  console.log("PASS: keyboard focus reaches the skill link after the copy button");

  for (const colorScheme of ["light", "dark"]) {
    await page.emulateMedia({ colorScheme });
    for (const width of [320, 375, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.locator("#agent-guide-heading").scrollIntoViewIfNeeded();
      const overflow = await page.evaluate(() => [...document.querySelectorAll("body *")].filter((element) => {
        const box = element.getBoundingClientRect();
        return box.width > 0 && box.right > innerWidth + 1 && getComputedStyle(element).position !== "absolute";
      }).map((element) => `${element.tagName}.${element.className}`).slice(0, 8));
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `${colorScheme} ${width}px overflow: ${overflow.join(", ")}`);
      assert.equal(await page.locator("#agent-prompt").isVisible(), true);
    }
  }
  console.log("PASS: 320px, 375px, and desktop layouts have no horizontal overflow in either color preference");

  await page.evaluate(() => {
    Object.defineProperty(navigator.clipboard, "writeText", { configurable: true, value: async () => { throw new DOMException("denied", "NotAllowedError"); } });
  });
  await button.click();
  await page.waitForFunction(() => document.querySelector("#agent-copy-status").textContent.includes("copy it manually"));
  assert.equal(await button.isEnabled(), true);
  console.log("PASS: simulated clipboard rejection offers manual copying and restores the button");

  const unavailable = await browser.newContext();
  await unavailable.addInitScript(() => Object.defineProperty(navigator, "clipboard", { value: undefined }));
  const unavailablePage = await unavailable.newPage();
  unavailablePage.on("pageerror", (error) => errors.push(error.message));
  await unavailablePage.goto(url);
  assert.equal(await unavailablePage.locator("#copy-agent-prompt").isHidden(), true);
  assert.equal(await unavailablePage.locator("#agent-prompt").innerText(), prompt);
  console.log("PASS: unavailable clipboard keeps the prompt readable and hides the control");

  const noScript = await browser.newContext({ javaScriptEnabled: false });
  const staticPage = await noScript.newPage();
  staticPage.on("pageerror", (error) => errors.push(error.message));
  await staticPage.goto(url);
  assert.equal(await staticPage.locator("#copy-agent-prompt").isHidden(), true);
  assert.equal(await staticPage.locator("#agent-prompt").innerText(), prompt);
  assert.equal(await staticPage.getByRole("link", { name: "View skill" }).isVisible(), true);
  assert.equal(await staticPage.locator(".challenge-card:visible").count(), await staticPage.locator(".challenge-card").count());
  assert.equal(await staticPage.locator(".catalog-pager").isHidden(), true);
  assert.deepEqual(errors, []);
  console.log("PASS: no-JavaScript prompt and skill link remain available; no page errors");
} finally {
  await browser?.close();
  await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
}
