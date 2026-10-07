# Evidence — PILOT-BUG-01

## Metadata

```yaml
artifact_type: evidence
format_version: 1
ticket_id: PILOT-BUG-01
round: 1
observed_commit: b5a13a883095151d53f69992345003267a828a9f
dirty_changes: []
created_at: 2026-10-07T12:11:09+00:00
scout_harness: trae
scout_model: DeepSeek-V4.1-Flash
task_type: bug
report_status: ready-for-audit
```

## Decision Questions

### DQ-01

**Question:** Why does `CachedValue.read()` still return `1` after `config["value"]` is changed from `1` to `2`?

**Decision affected:** Confirming the defect mechanism before any fix decision.

**Evidence targets:** `CachedValue.__init__`, `CachedValue.read`, and the runtime demo.

**Answer:** ANSWERED

**Facts:** F-01, F-02, F-03

### DQ-02

**Question:** Is the stale value caused by caching at construction time, or by a shared-reference problem in the caller?

**Decision affected:** Choosing the fix location (constructor, `read()`, or caller).

**Evidence targets:** Assignment semantics in `__init__`; mutation order in `demo.py`.

**Answer:** ANSWERED

**Facts:** F-01, F-02, F-03

### DQ-03

**Question:** Does any other code in the repository rely on observing `config["value"]` mutations after construction?

**Decision affected:** Scope of the fix and its regression surface.

**Evidence targets:** All Python files in the target root.

**Answer:** ANSWERED

**Facts:** F-04

## Findings

### F-01 [FACT]

**Statement:** `CachedValue.__init__` copies `config["value"]` into the instance attribute `self._value` at construction time; `read()` returns that stored attribute. No code path in `service.py` re-reads `config` after `__init__`.

**Questions:** DQ-01, DQ-02

**Sources:**
- code: service.py:1-3 :: CachedValue.__init__
- code: service.py:5-6 :: CachedValue.read

**Method:** static

**Scope:** `service.py` only; two methods, six executable lines. Says nothing about Python semantics beyond what is visible in source.

### F-02 [FACT]

**Statement:** Running the demo reproduces the stale value: it prints `initial=1`, `configured=2`, `actual=1` and exits `0`.

**Questions:** DQ-01, DQ-02

**Sources:**
- runtime: `python demo.py` / input: default config dict `{"value": 1}` mutated to `2` mid-run at demo.py:8 / observed result: stdout `initial=1`, `configured=2`, `actual=1` / exit status: 0

**Method:** execution

**Scope:** Single run on the observed commit `b5a13a883095`; no other Python version or platform tested.

### F-03 [INFERENCE]

**Statement:** The stale value is caused by copy-at-construction: `self._value = config["value"]` binds the immutable int object `1`, so later mutation of the dict cannot be observed by `read()`. Caller-side reordering alone cannot repair an already-constructed instance.

**Questions:** DQ-01, DQ-02

**Sources:**
- inference basis: F-01, F-02

**Basis:** F-01 shows the assignment happens only in `__init__`; F-02 shows the runtime effect. Python ints are immutable, so the bound object never changes after binding.

**Method:** inference

**Scope:** Inference from static reading plus one runtime observation; not a language-lawyer proof.

### F-04 [FACT]

**Statement:** No code other than `demo.py` constructs `CachedValue` or reads `config["value"]`; `demo.py` is the only consumer in the repository root.

**Questions:** DQ-03

**Sources:**
- negative search: scope target root `*.py` for `CachedValue(` and `config[` references / exclusions: the construction-time copy at service.py:3 and the demo construction at demo.py:6 / result: only demo.py:5-10 :: main touches `config["value"]` (mutation at demo.py:8) and calls `read()` (demo.py:7, demo.py:10); no post-construction re-read exists anywhere

**Method:** static

**Scope:** Target root Python files only; the vendored `.ai/workflow/examples/scout-fixture/` copy is a separate example fixture and not part of the target service.

## Unknowns

None. All in-scope decision questions (DQ-01, DQ-02, DQ-03) are answered by F-01 through F-04. Production callers outside this repository were not in scope and are not part of the ticket.

## Handoff

- **Established Fact IDs:** F-01, F-02, F-03, F-04
- **Decisions still required:** choose the fix shape — re-read inside `read()`, add an explicit reload path, or document construction-time immutability; and whether caller-visible semantics may change.
- **Missing evidence:** None for the current scope.
- **Already investigated:** full `service.py` and `demo.py` source; one runtime reproduction; scoped negative search of the target root for other consumers.
- **Stopping reason:** all in-scope questions are answered; no further repository behavior relevant to the defect remains to collect.
