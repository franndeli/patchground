# Last page of search results returns "page out of range"

**Reported by:** support (via customer ticket)
**Component:** `catalog.pagination`

## Symptom

Customers browsing search results can't reach the last few products. Clicking the final page
link shows an error instead of the remaining items. The pager also hides the "Next" button one
page too early.

It does not happen for every search: a search for "lamp" (40 results) pages fine, a search for
"chair" (25 results) does not.

## Reproduction

```python
from catalog.pagination import paginate

results = [f"chair-{i}" for i in range(25)]

paginate(results, page=1, per_page=10)   # works, 10 items
paginate(results, page=2, per_page=10)   # works, 10 items
paginate(results, page=3, per_page=10)   # raises PageOutOfRange
```

## Expected

25 results at 10 per page are 3 pages: 10, 10 and 5 items. Page 3 returns the last 5 items,
`total_pages` is 3, and page 2 reports `has_next=True`.

## Actual

`total_pages` is 2, page 2 reports `has_next=False`, and page 3 raises `PageOutOfRange`.

## Notes

- Requesting a page past the real end (e.g. page 4 above) must keep raising `PageOutOfRange`;
  the web layer turns it into a 404.
- An empty result set is still a single, empty page 1.
- Run the tests with `pytest`.
