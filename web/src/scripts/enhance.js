"use strict";

// Progressive enhancement only. Without JavaScript every challenge, pack, link and command is visible.

// --- Challenge filtering and search ----------------------------------------------------------

const filters = [...document.querySelectorAll("[data-filter]")];
const challenges = [...document.querySelectorAll("[data-facets]")];
const count = document.querySelector("#catalog-count");
const filterGroup = document.querySelector(".filters");
const searchBox = document.querySelector("#catalog-search");
const emptyNote = document.querySelector("#catalog-empty");

if (filterGroup && count && challenges.length && filters.length) {
  const summary = count.dataset.summary || count.textContent;
  let facet = "all";
  let query = "";

  const apply = () => {
    let visible = 0;
    for (const challenge of challenges) {
      const facets = (challenge.dataset.facets || "").split(/\s+/);
      const haystack = challenge.dataset.search || "";
      challenge.hidden = (facet !== "all" && !facets.includes(facet)) || (query !== "" && !haystack.includes(query));
      if (!challenge.hidden) visible += 1;
    }
    if (emptyNote) emptyNote.hidden = visible !== 0;
    const parts = [];
    if (facet !== "all") parts.push(facet);
    if (query) parts.push(`“${query}”`);
    count.textContent = parts.length
      ? `${visible} ${visible === 1 ? "challenge" : "challenges"} · ${parts.join(" · ")}`
      : summary;
  };

  for (const button of filters) {
    button.addEventListener("click", () => {
      facet = button.dataset.filter;
      for (const other of filters) other.setAttribute("aria-pressed", String(other === button));
      apply();
    });
  }
  filterGroup.hidden = false;

  if (searchBox) {
    searchBox.closest("label").hidden = false;
    searchBox.addEventListener("input", () => {
      query = searchBox.value.trim().toLowerCase();
      apply();
    });
  }
}

// --- Pack sorting ----------------------------------------------------------------------------

const packGrid = document.querySelector("#pack-grid");
const packSort = document.querySelector("#pack-sort");

if (packGrid && packSort) {
  const cards = [...packGrid.querySelectorAll(".pack-card")];
  const keys = {
    stars: (c) => Number(c.dataset.stars),
    verified: (c) => Date.parse(c.dataset.verified) || 0,
    newest: (c) => Date.parse(c.dataset.firstSeen) || 0,
    count: (c) => Number(c.dataset.count),
  };
  const sort = () => {
    const key = keys[packSort.value] || keys.stars;
    // Built-in packs have no host stats; they keep their place at the top for every sort.
    const sorted = cards.slice().sort((a, b) => {
      if (a.dataset.kind !== b.dataset.kind) return a.dataset.kind === "built-in" ? -1 : 1;
      return key(b) - key(a);
    });
    for (const card of sorted) packGrid.append(card);
    const empty = packGrid.querySelector(".packs-empty");
    if (empty) packGrid.append(empty);
  };
  packSort.closest("label").hidden = false;
  packSort.addEventListener("change", sort);
}

// --- Copy setup commands and agent prompt -----------------------------------------------------

const copyTargets = [
  {
    button: "#copy-command", content: "#install-command", status: "#copy-status",
    success: "Copied. Paste into your terminal when you’re ready.",
    failure: "Couldn’t copy. Select the commands above and copy them manually.",
  },
  {
    button: "#copy-agent-prompt", content: "#agent-prompt", status: "#agent-copy-status",
    success: "Copied. Paste into your AI assistant when you’re ready.",
    failure: "Couldn’t copy. Select the prompt above and copy it manually.",
  },
];

for (const target of copyTargets) {
  const button = document.querySelector(target.button);
  const content = document.querySelector(target.content);
  const status = document.querySelector(target.status);
  if (!button || !content || !status || !navigator.clipboard?.writeText) continue;

  button.hidden = false;
  button.addEventListener("click", async () => {
    button.disabled = true;
    status.textContent = "";
    try {
      await navigator.clipboard.writeText(content.textContent.trim());
      status.textContent = target.success;
    } catch {
      status.textContent = target.failure;
    } finally {
      button.disabled = false;
    }
  });
}

// --- Pointer spotlight on cards ---------------------------------------------------------------

for (const card of document.querySelectorAll("[data-spotlight]")) {
  card.addEventListener("pointermove", (event) => {
    const box = card.getBoundingClientRect();
    card.style.setProperty("--x", `${event.clientX - box.left}px`);
    card.style.setProperty("--y", `${event.clientY - box.top}px`);
  });
}
