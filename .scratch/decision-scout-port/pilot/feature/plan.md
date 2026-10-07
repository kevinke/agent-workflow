# Plan - PILOT-FEAT-01

## Metadata

```yaml
artifact_type: plan
format_version: 1
ticket_id: PILOT-FEAT-01
task_count: 2
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

## Task 2

### Objective
Complete the persisted handoff for the reload change: replace every placeholder
in .ai/work/PILOT-FEAT-01/handoff.md with concrete, verified contents so the
cross-harness handoff obligation is satisfied. No production-code change.

### Inputs
- review.md finding (verdict changes_requested): the only gap is the unfilled
  handoff template; the reload implementation and both acceptance commands
  already pass.
- Current repository identity (branch, HEAD, uncommitted state) and the artifact
  hashes as re-verified during this task.
- Task 1's acceptance commands, re-run to produce fresh execution evidence.

### Allowed changes
- .ai/work/PILOT-FEAT-01/handoff.md
- .ai/work/PILOT-FEAT-01/progress.md
- .ai/work/PILOT-FEAT-01/state.yaml (written only through the workflow CLI)

### Protected scope
- Do not modify service.py, demo.py, or any other production file.
- Do not modify review.md (its verdict and hash are bound in state.yaml),
  plan.md (registered), evidence.md, or evidence-audit.md.
- Do not alter Task 1's registered section; its canonical hash must survive.

### Invariants
- Task 1 canonical hash remains 9063ea957a720252ac54b734e96fdec5f91025750f9766dac58902676c173294.
- review.md raw-byte sha256 remains 8bc6e0e6fddee140b0a8812a979e0672ddd12cff02f12870ccf9f6433ff80d1c.
- state.yaml is only ever written by the ai-workflow CLI.

### Acceptance criteria
- handoff.md has every required section filled with verified values; the
  placeholder probe `Select-String -Path .ai\work\PILOT-FEAT-01\handoff.md -Pattern '<[a-z ]+>'`
  returns no matches.
- Both Task 1 acceptance commands re-run green: prints 5, then prints 7.
- `validate PILOT-FEAT-01` reports OK with no ERROR findings.

### Verification
Command 1 (placeholder probe; expect no matches):
`Select-String -Path .ai\work\PILOT-FEAT-01\handoff.md -Pattern '<[a-z ]+>'`
Command 2 (expect prints 5, exit 0):
`$env:PYTHONDONTWRITEBYTECODE=1; python -c "from service import CachedValue; c = CachedValue({'value': 1}); c.reload({'value': 5}); print(c.read())"`
Command 3 (expect prints 7, exit 0):
`$env:PYTHONDONTWRITEBYTECODE=1; python -c "from service import CachedValue; src = {'value': 7}; c = CachedValue({'value': 1}); c.reload(src); src['value'] = 9; print(c.read())"`
Command 4 (expect validate OK):
`python d:\Codegent-workflow\scriptsi-workflow\main.py validate PILOT-FEAT-01`

### Dependencies
Task 1 (the reload implementation whose handoff this task completes).

### Escalation conditions
- Completing the handoff would require touching a protected file (review.md,
  plan.md, evidence.md, evidence-audit.md, service.py, demo.py).
- The re-review demands further production-code changes or a different design.
