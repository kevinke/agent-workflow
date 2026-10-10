# Technical Decision — PAIR-01

## Chosen approach

Add the required public `Config.reload() -> None` boundary in `config.py`.
`Config` will retain its constructor path as a private per-instance field.
Reload will first construct a complete replacement `ValueCache` from that path
in a local variable and assign it to `self._cache` only after construction
succeeds. `cache.py` and `ValueCache` require no behavioral or API change.

This resolves DQ-01 by retaining cache ownership on each `Config` instance
(F-02–F-04), DQ-02 by making replacement deferred until the existing parser has
fully succeeded (F-05–F-07), and DQ-03 by placing the sole new public method on
the already-public `Config` facade while keeping cache internals private
(F-01, F-09).

## Rejected alternatives

- Add `ValueCache.reload()` that mutates `_values`: rejected because it expands
  the cache object's method surface and requires a second transactional update
  path when constructing a replacement already provides deferred commit.
- Parse directly into the existing `_values` dictionary: rejected because a
  mid-file `ValueError` could expose a partial update and violate required
  failure preservation.
- Share caches by source path: rejected because existing ownership and required
  behavior are per instance (F-02–F-04).

## Invariants

- `get` continues to read only the current instance's cached values.
- File changes remain invisible until `reload` is explicitly called.
- A reload failure leaves the exact prior `ValueCache` object installed, so all
  previously cached keys and values remain available.
- Reloading one `Config` cannot mutate another instance, including when both use
  the same path.
- Existing stripping, comment/blank-line handling, first-`=` splitting, error
  types/messages, missing-key behavior, and UTF-8 reading remain unchanged.

## Compatibility

`Config(path: str)` and `Config.get(key: str) -> str` retain their existing
behavior. The only public addition is the task-required `Config.reload() ->
None`. `ValueCache` remains an internal implementation detail with its existing
constructor and `get` behavior. Python 3 standard library remains the only
dependency.

## API / schema decisions

- Public API: add exactly `Config.reload(self) -> None`.
- Private state: add a per-instance path field on `Config`; do not expose it or
  expose the mutable cache dictionary.
- Persistence/schema: none.
- Error contract: propagate the existing `ValueError` from replacement
  `ValueCache` construction; do not catch, wrap, or translate it.

## Risks

- Assigning `self._cache` before replacement construction finishes would break
  failure atomicity; assignment must be the final operation.
- Reusing or globally indexing a `ValueCache` would break instance isolation.
- Duplicating parsing in `Config` could drift from existing behavior; the
  implementation must reuse `ValueCache(path)`.

## Escalation boundaries

Escalate instead of improvising if acceptance requires changing `test_behavior.py`,
the frozen task, parser semantics/error messages, any public API beyond
`Config.reload`, files outside `config.py` and `cache.py`, or dependencies
outside the Python 3 standard library.
