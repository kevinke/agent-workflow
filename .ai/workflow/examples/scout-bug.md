# Evidence — SCOUT-001 (bug example: stale cached value)

Worked example of the Scout Report contract on the committed fixture under
`.ai/workflow/examples/scout-fixture/`. The scenario: `CachedValue` keeps
returning the initial value after its config dict is updated.

## Metadata

```yaml
artifact_type: evidence
format_version: 1
ticket_id: SCOUT-001
round: 1
observed_commit: bceba0fb81f6dad3e2c7dfb6fe4c89b61e7bbe7e
dirty_changes:
  - .ai/workflow/examples/scout-fixture/service.py
  - .ai/workflow/examples/scout-fixture/demo.py
created_at: 2026-10-07
scout_harness: trae
scout_model: trae-proprietary
task_type: bug
report_status: ready-for-audit
```

Observed snapshot: `observed_commit` is the repository HEAD when this report
was written. The fixture files were new (untracked) working-tree changes at
that moment; they are listed in `dirty_changes` so every anchor below can be
re-checked against that exact state.

## Decision Questions

### DQ-01

**Question:** Why does `CachedValue.read()` still return `1` after `config["value"]` is updated from `1` to `2`?

**Decision affected:** Confirming the defect mechanism before any fix decision.

**Evidence targets:** `CachedValue.__init__`, `CachedValue.read`, the runtime demo.

**Answer:** ANSWERED

**Facts:** F-01, F-02, F-03

### DQ-02

**Question:** Is the stale value caused by caching at construction time, or by a shared-reference problem in the caller?

**Decision affected:** Choosing the fix location (constructor, `read()`, or caller).

**Evidence targets:** Assignment semantics in `__init__`; `demo.py` mutation order.

**Answer:** ANSWERED

**Facts:** F-01, F-02, F-03

### DQ-03

**Question:** Does any other code in the fixture rely on observing `config["value"]` mutations after construction?

**Decision affected:** Scope of the fix and its regression surface.

**Evidence targets:** All Python files in `.ai/workflow/examples/scout-fixture/`.

**Answer:** UNKNOWN

**Facts:** F-04; UNKNOWN — usage outside the fixture is out of scope for this report.

## Findings

### F-01 [FACT]

**Statement:** `CachedValue.__init__` copies `config["value"]` into the instance attribute `self._value` at construction time; `read()` returns that stored attribute. No code path re-reads `config` after `__init__`.

**Questions:** DQ-01, DQ-02

**Sources:**
- code: .ai/workflow/examples/scout-fixture/service.py:2-3 :: CachedValue.__init__
- code: .ai/workflow/examples/scout-fixture/service.py:5-6 :: CachedValue.read

**Method:** static

**Scope:** Fixture only; two files, nine executable lines. Says nothing about Python semantics beyond what is visible in source.

### F-02 [FACT]

**Statement:** Running the demo reproduces the stale value: it prints `initial=1`, `configured=2`, `actual=1` and exits `0`.

**Questions:** DQ-01, DQ-02

**Sources:**
- runtime: `python demo.py` (cwd `.ai/workflow/examples/scout-fixture`) / input: default config dict `{"value": 1}` mutated to `2` mid-run / observed result: stdout `initial=1`, `configured=2`, `actual=1` / exit status: 0

**Method:** execution

**Scope:** Single run on the observed commit plus dirty fixture; no other Python version or platform tested.

### F-03 [INFERENCE]

**Statement:** The stale value is caused by copy-at-construction: `self._value = config["value"]` binds the immutable int object `1`, so later mutation of the dict cannot be observed by `read()`. Any fix must either re-read `config` inside `read()` or expose an explicit reload path; caller-side reordering alone cannot repair an already-constructed instance.

**Questions:** DQ-01, DQ-02

**Sources:**
- inference basis: F-01, F-02

**Basis:** F-01 shows the assignment happens only in `__init__`; F-02 shows the runtime effect. Python ints are immutable, so the bound object never changes after binding.

**Method:** inference

**Scope:** Inference from static reading plus one runtime observation; not a language-lawyer proof.

### F-04 [FACT]

**Statement:** No other module in the fixture reads `config["value"]`; `demo.py` is the only consumer.

**Questions:** DQ-03

**Sources:**
- negative search: scope `.ai/workflow/examples/scout-fixture/*.py` for `config[` / `read(` references / exclusions: the construction-time copy at `.ai/workflow/examples/scout-fixture/service.py:3` / result: only `.ai/workflow/examples/scout-fixture/demo.py:5-10 :: main` re-touches the key (mutation at line 8) and calls `read()` (lines 7, 10); no post-construction re-read exists anywhere

**Method:** static

**Scope:** Fixture directory only; consumer code elsewhere in any adopting repository was not searched.

## Reproduction

1. `cd .ai/workflow/examples/scout-fixture`
2. `python demo.py`
3. Observed: `initial=1`, `configured=2`, `actual=1`; exit `0`.

Reproduction established on the observed commit with the dirty fixture paths
listed in Metadata.

## Failure Boundary

The failure boundary is exact: any mutation of `config["value"]` after
`CachedValue(config)` construction is invisible to `read()`. Mutating other
keys, or constructing a new `CachedValue` with the updated dict, behaves
correctly. Whether a production failure boundary exists outside the fixture is
unknown (see DQ-03); establishing it was not possible within this report's
scope, and it is recorded as unknown rather than guessed.

## Unknowns

- **U-01 / DQ-03, F-04:** Whether any caller outside the fixture constructs `CachedValue` and then mutates the config dict. Impact: decides whether the fix must preserve construction-time semantics for existing callers or may change them. Next collection step: search the consuming repository for `CachedValue(` constructions before the fix decision.

## Handoff

- **Established Fact IDs:** F-01, F-02, F-03, F-04
- **Decisions still required:** choose the fix shape — re-read inside `read()`, add an explicit `reload()`, or document construction-time immutability; and whether caller-visible semantics may change.
- **Missing evidence:** `CachedValue` usage outside the fixture (U-01).
- **Already investigated:** full fixture source; one runtime reproduction; scoped negative search of the fixture directory.
- **Stopping reason:** all in-scope questions are answered; the single remaining gap (external usage) is precisely named with a next collection step and requires a consumer-search decision, not more fixture investigation.
