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

// --- Copy install commands -------------------------------------------------------------------

const copyButton = document.querySelector("#copy-command");
const command = document.querySelector("#install-command");
const copyStatus = document.querySelector("#copy-status");

if (copyButton && command && copyStatus && navigator.clipboard?.writeText) {
  copyButton.hidden = false;
  copyButton.addEventListener("click", async () => {
    copyButton.disabled = true;
    copyStatus.textContent = "";
    try {
      await navigator.clipboard.writeText(command.textContent.trim());
      copyStatus.textContent = "Copied. Paste into your terminal when you’re ready.";
    } catch {
      copyStatus.textContent = "Couldn’t copy. Select the commands above and copy them manually.";
    } finally {
      copyButton.disabled = false;
    }
  });
}
