# Plan - PILOT-FEAT-01

## Metadata

```yaml
artifact_type: plan
format_version: 1
ticket_id: PILOT-FEAT-01
task_count: 1
```

## Task 1

### Objective
Add `reload(self, config: dict) -> None` to `CachedValue`. It replaces the
cached value with `config["value"]` using the same one-time extraction as
`__init__` (snapshot, no retained reference to the mapping) and returns None.
Leave `__init__` and `read` unchanged.

### Inputs
Facts F-01 (no reload exists; service.py:1-6), F-02 (value stored in
self._value at construction; no retained config reference), F-04 (demo.py is
the only consumer), F-05 (adding a method cannot break non-existent callers),
and the chosen approach in decision.md.

### Allowed changes
service.py, within the `CachedValue` class body only.

### Protected scope
- Do not change `__init__` behavior or its `(self, config: dict) -> None` signature.
- Do not change `read` behavior or its `(self) -> int` signature.
- Do not modify demo.py.
- Do not add imports, new modules, or new files.

### Invariants
- `read()` continues to return the stored integer and, before any reload, the
  value captured at construction.
- `reload` returns `None` and performs exactly one extraction of `config["value"]`.
- `reload` holds no reference to the mapping after it returns (snapshot
  semantics); subsequent mutation of the source dict is not reflected.

### Acceptance criteria
- After `c = CachedValue({"value": 1})` then `c.reload({"value": 5})`,
  `c.read()` returns `5`.
- Snapshot semantics: after `src = {"value": 7}` (a mapping), `c = CachedValue({"value": 1})`,
  `c.reload(src)`, then `src["value"] = 9`, `c.read()` returns `7`.
- `__init__` and `read` behavior is unchanged and no other file is modified.

### Verification
Command 1: `$env:PYTHONDONTWRITEBYTECODE=1; python -c "from service import CachedValue; c = CachedValue({'value': 1}); c.reload({'value': 5}); print(c.read())"`
Expected outcome 1: prints `5` and exits 0.

Command 2: `$env:PYTHONDONTWRITEBYTECODE=1; python -c "from service import CachedValue; src = {'value': 7}; c = CachedValue({'value': 1}); c.reload(src); src['value'] = 9; print(c.read())"`
Expected outcome 2: prints `7` and exits 0 (snapshot is not aliased).

### Dependencies
N/A

### Escalation conditions
- Meeting the acceptance criteria would require changing `__init__` or `read`,
  editing demo.py, or adding files, imports, or tests.
- The reviewer requires live-reference semantics or a different signature or
  return value for `reload`.
