# PAIR-01: explicit, failure-safe configuration reload

Status: frozen preparation; feature intentionally absent
Prepared: 2026-10-10
Authority: HARDEN-009 development plan, Task 1; supplemental spec C9

## User-visible behavior

The starting fixture reads UTF-8 `key=value` configuration. Blank lines and
lines whose stripped text starts with `#` are ignored. `Config(path: str)` and
`Config.get(key: str) -> str` already exist. Values remain cached for each
instance, even after its source file changes.

Implement `Config.reload() -> None` so that:

1. Ordinary reads retain initial values until an explicit reload.
2. Reload reads a valid changed file and exposes the new values.
3. A malformed reload raises `ValueError` and preserves every previously
   cached value, including values parsed before the malformed line.
4. Different `Config` instances do not share cache mutations, even when they
   refer to the same source path. Reloading one leaves the other's values intact.
5. Existing parsing and `get` behavior remain compatible.

## Decision Questions to investigate

- DQ-01: Where do parsed values live, how long do they survive, and which
  ownership paths could accidentally couple two instances?
- DQ-02: What observable parser/error behavior already exists, and what must
  be preserved when reload fails after some valid input has been consumed?
- DQ-03: Which module boundary can support reload and independent verification
  without exposing mutable cache internals or broadening the public API?

These are questions, not supplied answers. The Scout must anchor findings to
the actual starting revision and label FACT, INFERENCE and UNKNOWN. The senior
receiver decides the implementation seam from the persisted Evidence.

## Scope

- Implementation may change only `config.py` and `cache.py` in the disposable
  target, plus the workflow artifacts owned by its current role.
- `test_behavior.py`, this frozen task, and installed Protocol/role/contract
  documents are protected. A necessary acceptance change requires escalation.
- Use Python 3 standard library only. Do not modify kit production code or
  historical SCOUT-008 evidence. Do not add auto-dispatch infrastructure.
- The preparation copy intentionally has no `reload` method. The receiving
  implementation, decision and technical verdict must come from live sessions.

## Acceptance command

From the disposable target root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s . -p 'test_behavior.py' -v
```

Passing requires all five named cases and exit 0: `test_reads_initial`,
`test_cached_until_reload`, `test_reload_valid`,
`test_bad_reload_preserves_previous`, and `test_instances_isolated`.

The prepared starting revision is expected to pass read/isolation cases and
error in the other three solely because `Config.reload` is missing. That red
baseline is a preparation observation, never passing live acceptance.
