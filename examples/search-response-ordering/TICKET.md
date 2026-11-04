# Old search results replace the latest query

Catalog support has a reproducible report: search for one part, immediately search
for another, and sometimes the results jump back to the first part. Clearing the
search box or leaving the catalog can also be followed by an unexpected state change.

Fix `src/search-model.ts` without adding a framework or changing its public API.
Add a regression check under `tests/`. This is a state-model task, not a visual UI task.

## Public API and state

`new SearchModel(transport: SearchTransport)` injects a function
`(query: string) => Promise<string[]>`. It supplies ordered catalog labels.
`model.get_state()` returns the current readonly `SearchState`. Call it again
to read changes; callers must not mutate state or its results. No subscription API is required.

Every state has `kind`, `query`, `results` and `error`:

- Initial/cleared: `{ kind: "idle", query: "", results: [], error: null }`.
- Loading: `{ kind: "loading", query: trimmedQuery, results: [], error: null }`.
- Success: `{ kind: "ready", query: trimmedQuery, results: transportResults, error: null }`.
- Failure: `{ kind: "error", query: trimmedQuery, results: [], error: message }`.
  For an `Error` rejection use its message; for any other rejection use `"Search failed"`.

## Required behavior

`model.search(input: string): Promise<void>` updates loading/idle state immediately
when called, before any transport promise settles.

1. Trim the input. For a nonempty query, clear previous results and errors, enter
   loading and call the transport exactly once with the trimmed query.
2. Only the latest request may commit success **or failure**. A stale success must not
   replace newer state, including while the latest request is still loading. A stale
   failure must not overwrite a newer success or error.
3. Whitespace-only input invalidates all in-flight work and enters the empty idle state
   without a transport call. Later completion of older work must leave it idle.
4. Repeating exactly the same trimmed query still starts a fresh request. The earlier
   request becomes stale even though the text is identical.
5. A current failure clears results and enters the documented error state.
   Search can recover by starting another request, which clears that error.
6. A successful transport may return an empty list; this is a ready state, not idle.
   Preserve result order.
7. `model.dispose(): void` invalidates all in-flight requests. It leaves the current
   state unchanged. All later search calls (including clears) are no-ops and do not
   call the transport. Repeated disposal is harmless.

The returned search promise settles after its own transport settles and handles
transport rejection without rejecting to the caller, even for stale/disposed work.
Invalidation does not require aborting or settling a still-pending transport.
Separate model instances have independent request ownership and disposal. Assume input
types are valid and the transport honors its promise-returning signature.

## Constraints and verification

Use explicit promise controls to test completion order, not real HTTP, wall-clock
sleeps or assumed timing. No debounce, cancellation support, timers, DOM, backend or new
dependencies are required. Preserve the supplied environment and runner.
Use `pgnd check` in a session; all challenge commands run in Docker.
Hidden checks combine only the public state and lifecycle requirements above.

This original exercise was AI-generated. The intermediate difficulty and 45-minute
timebox are provisional author estimates, not human calibration or an employer endorsement.
