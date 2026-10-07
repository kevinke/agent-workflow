# Plan - PILOT-BUG-01

## Metadata

```yaml
artifact_type: plan
format_version: 1
ticket_id: PILOT-BUG-01
task_count: 1
```

## Task 1

### Objective
Change `CachedValue` so `read()` returns the current value from the config
mapping instead of a value copied at construction time. Store the mapping in
`__init__` and read `config["value"]` on each call, removing the
copy-at-construction that causes the stale read.

### Inputs
Facts F-01 (service.py:1-3, service.py:5-6 copy-at-construction), F-03
(copy-at-construction is the cause), F-04 (demo.py is the only consumer), and
the chosen approach in decision.md.

### Allowed changes
service.py, within the `CachedValue` class body only.

### Protected scope
- Do not modify demo.py or its expected output contract.
- Do not change the `__init__(self, config: dict) -> None` signature.
- Do not change the `read(self) -> int` signature or return type.
- Do not add imports or new modules.

### Invariants
- `CachedValue(config)` still accepts a dict and `read()` still returns an int
  for a well-formed config containing `"value"`.
- No behavior change for configs that are never mutated after construction.

### Acceptance criteria
- After `config["value"] = 2`, `cached.read()` returns `2` for an instance
  constructed from that same `config`.
- `python demo.py` prints `initial=1`, `configured=2`, `actual=2` and exits 0.
- No other file in the repository is modified.

### Verification
Command: `$env:PYTHONDONTWRITEBYTECODE=1; python demo.py`
Expected outcome: stdout lines `initial=1`, `configured=2`, `actual=2` in that
order and process exit status 0.

### Dependencies
N/A

### Escalation conditions
- Meeting the acceptance criteria would require editing demo.py, changing the
  constructor signature, or changing the `read()` return type.
- The reviewer requires snapshot semantics to be preserved for this bug.
