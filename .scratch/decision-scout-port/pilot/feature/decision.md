# Decision - PILOT-FEAT-01

## Chosen approach

Add a `reload(self, config: dict) -> None` method to `CachedValue` that replaces
the cached value by extracting `config["value"]` once, using the same extraction
semantics as `__init__`, and returns `None`. The method does not retain a
reference to the mapping, so it is a snapshot replacement: after `reload`,
`read()` returns the new value, and later mutation of the source dict is not
observed. `__init__` and `read` are left unchanged.

## Rejected alternatives

- Live or aliasing reload that stores the config mapping so later mutations are
  seen. Rejected: the ticket specifies snapshot-replacement semantics (the same
  extraction as `__init__`), and a retained reference would violate that
  contract.
- Change `read()` to read a live value. Rejected: out of scope; `read()`
  semantics are protected and belong to the separate bug ticket, not here.
- Implement the behavior as a module-level helper or a subclass. Rejected: the
  requested public surface is a method on the existing `CachedValue` class.

## Invariants

- `__init__(self, config: dict) -> None` signature and behavior are unchanged.
- `read(self) -> int` signature and behavior are unchanged; it returns the
  currently stored integer.
- `reload` returns `None` and extracts `config["value"]` exactly once.
- `reload` keeps no reference to the passed mapping after it returns.

## Compatibility

- Purely additive. F-05 establishes `demo.py` as the only in-repo consumer, so
  adding a method cannot break an existing caller; no in-repo test or other
  importer exists to update.
- No new imports or dependencies; the class stays dependency-free and
  stdlib-only.

## Risks

- Calling `reload` with a mapping that lacks `"value"` raises `KeyError`, which
  matches the existing `__init__` behavior for the same input and introduces no
  new failure mode.
- Passing a non-mapping raises `TypeError` on subscription, consistent with
  `__init__`.

## Escalation boundaries

- Escalate if the reviewer requires live-reference or aliasing semantics, a
  different signature or return value, or any change to `__init__` or `read`.
- Escalate if acceptance depends on retaining the passed mapping after `reload`,
  since that contradicts the specified snapshot-replacement contract.
