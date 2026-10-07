# Decision - PILOT-BUG-01

## Chosen approach

Make `CachedValue` hold a reference to the caller's config mapping and read the
current value on each call, so `read()` observes later mutation of the same
dict. Concretely: store the mapping in `__init__` (for example `self._config =
config`) and have `read()` return `self._config["value"]`. This removes the
copy-at-construction that F-01/F-03 identify as the cause and makes the demo
observe the updated value after `config["value"] = 2`.

## Rejected alternatives

- Keep the construction-time copy and add an explicit reload method. Rejected
  for the bug: the reported repro (demo.py) never calls such a method, so the
  stale read at demo.py:10 would remain. The explicit reload API is the
  separate PILOT-FEAT-01 feature and is deliberately not pulled into this fix.
- Document construction-time immutability and require callers to reorder.
  Rejected: F-03 shows reordering cannot repair an already-constructed
  instance, and it contradicts the defect expectation that `read()` after the
  mutation returns the new value.
- Fix in the caller (demo.py only). Rejected: this leaves the class itself
  stale and does not correct the defect at its source.

## Invariants

- `CachedValue.__init__(self, config: dict) -> None` signature is unchanged.
- `CachedValue.read(self) -> int` signature and return type are unchanged.
- `read()` keeps returning the value under the key `"value"` and does not add
  new failure modes for a well-formed config dict.
- No new imports or dependencies; the class stays dependency-free.

## Compatibility

- Public constructor and method signatures are preserved, so existing
  construction sites keep working. F-04 confirms demo.py is the only consumer
  in the repository, so the observable semantic surface is limited to it.
- Semantic change is intentional and bounded: `read()` becomes a live view of
  the same mapping (later in-place mutation is reflected) instead of a snapshot
  taken at construction. Snapshot-style behavior, when required, belongs to the
  explicit reload API in PILOT-FEAT-01, not to this fix.
- Config that is replaced rather than mutated (a new dict object) is still not
  observed; that is out of scope for this bug.

## Risks

- Callers that deliberately relied on snapshot semantics would see different
  results after in-place mutation. F-04 bounds this to demo.py, where the new
  behavior is the desired outcome, so the risk is acceptable for this change.
- Storing a reference keeps the caller's dict alive for the instance lifetime;
  this is negligible for the in-repo usage and introduces no leak concern.

## Escalation boundaries

- Escalate if a reviewer requires preserving snapshot semantics for callers
  outside this repository, or if the intended fix is a documented-immutability
  contract rather than a live read.
- Escalate if the change cannot satisfy the demo expectation (initial=1,
  configured=2, actual=2) without altering `demo.py`, the constructor signature,
  or the `read()` return type.
