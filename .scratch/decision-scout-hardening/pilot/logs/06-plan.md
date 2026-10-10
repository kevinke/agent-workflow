# Plan — PAIR-01

## Metadata

```yaml
artifact_type: plan
format_version: 1
ticket_id: PAIR-01
task_count: 1
```

## Task 1

### Objective

Implement explicit, failure-atomic per-instance configuration reload at the
decided `Config` boundary, then verify all frozen acceptance behaviors.

### Inputs

- Evidence F-01 through F-09, especially per-instance ownership (F-02–F-04),
  existing parser/deferred construction behavior (F-05–F-06), and the absent
  reload boundary (F-07, F-09).
- `decision.md`: retain the path privately on each `Config`; add exactly
  `Config.reload() -> None`; construct a complete replacement `ValueCache`
  locally and assign it only after successful construction.

### Allowed changes

- `config.py`: add the private per-instance path retention and the decided
  `reload` method.
- Executor-owned `.ai/work/PAIR-01/progress.md`, `handoff.md`, and state updates
  made through public workflow commands.

### Protected scope

- Do not change `cache.py`, `test_behavior.py`, `task.md`, installed workflow or
  skill documents, or any other production/test file.
- Do not expose cache internals, add other public APIs, alter parser/error/get
  semantics, introduce shared cache state, or add dependencies.

### Invariants

- Ordinary reads remain cached until explicit reload.
- A failed reload leaves the exact prior cache installed and all prior values
  observable.
- Every `Config` continues to own independent cache state, even for a shared
  source path.
- Existing UTF-8 parsing, blank/comment handling, whitespace stripping,
  first-`=` splitting, `ValueError` behavior, and missing-key behavior remain
  unchanged.

### Acceptance criteria

- `Config.reload()` returns `None` after a valid reload and subsequent `get`
  calls expose all newly parsed values.
- File changes remain invisible before explicit reload.
- A malformed reload raises the existing `ValueError` and every prior cached
  value remains unchanged, including when valid lines precede the bad line.
- Reloading one of two instances on the same path does not alter the other.
- All five frozen tests named in `task.md` pass with exit status 0.

### Verification

Run from the repository root:

`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s . -p 'test_behavior.py' -v`

Expected: exit 0 and `ok` for `test_reads_initial`,
`test_cached_until_reload`, `test_reload_valid`,
`test_bad_reload_preserves_previous`, and `test_instances_isolated`, with no
errors or failures.

### Dependencies

N/A — this is the only implementation task.

### Escalation conditions

Escalate rather than improvise if satisfying acceptance appears to require a
change outside `config.py`, any parser/error/API behavior beyond the recorded
decision, modification of protected files, a non-standard-library dependency,
or deviation from replacement-before-assignment failure atomicity.
