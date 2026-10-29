# Debrief questions

1. The visible tests were green before you changed anything. What made you trust (or distrust)
   that baseline, and how did you confirm the bug before touching the code?
2. Walk me through the boundary cases you considered for the page count: empty results, fewer
   items than one page, exact multiples, one item over a multiple. Which one would you add as a
   regression test first, and why?
3. The web layer turns `PageOutOfRange` into a 404. If your fix had made every page number valid,
   how would that have shown up in production, and how would you have noticed?
