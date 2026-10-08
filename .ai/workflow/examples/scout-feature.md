# Evidence — SCOUT-001 (feature example: explicit `reload()`)

Worked example of the Scout Report contract on the committed fixture under
`.ai/workflow/examples/scout-fixture/`. The scenario: investigate adding an
explicit `reload()` to `CachedValue` — without implementing it. This report is
deliberately **partial**: it carries a critical UNKNOWN and shows why only the
evidence-auditor can open the Evidence Gate.

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
task_type: feature
report_status: partial
```

Observed snapshot: same snapshot as the bug example — `observed_commit` is the
repository HEAD when this report was written, and the fixture files were new
untracked changes listed in `dirty_changes`, so every anchor can be re-checked
against that exact state.

## Decision Questions

### DQ-01

**Question:** What should `reload()` do exactly — re-read only `config["value"]`, or re-validate and re-copy the whole config dict?

**Decision affected:** The API shape and its contract with callers.

**Evidence targets:** `CachedValue.__init__` storage layout; existing mutation behavior observed by `demo.py`.

**Answer:** UNKNOWN

**Facts:** F-01, F-02; UNKNOWN — this is an architectural choice, escalated rather than answered by the scout.

### DQ-02

**Question:** Is there any existing reload/update/refresh path in the fixture that a new `reload()` would conflict with or duplicate?

**Decision affected:** Whether the change is purely additive.

**Evidence targets:** All Python files in `.ai/workflow/examples/scout-fixture/`.

**Answer:** ANSWERED

**Facts:** F-01, F-03

### DQ-03

**Question:** What runtime behavior would `reload()` need to preserve or change, given how the stale value manifests today?

**Decision affected:** Acceptance criteria and regression surface for the future change.

**Evidence targets:** The observed `demo.py` output.

**Answer:** ANSWERED

**Facts:** F-02

## Findings

### F-01 [FACT]

**Statement:** `CachedValue` stores a single value copied from `config["value"]` in `__init__` and exposes only `read()`; there is no existing reload, update, or refresh method.

**Questions:** DQ-01, DQ-02

**Sources:**
- code: .ai/workflow/examples/scout-fixture/service.py:1-6 :: CachedValue (class body, `__init__`, `read`)

**Method:** static

**Scope:** Fixture only; the class body is six lines.

### F-02 [FACT]

**Statement:** After `config["value"]` is mutated from `1` to `2`, `read()` still returns `1`; the demo prints `initial=1`, `configured=2`, `actual=1` and exits `0`.

**Questions:** DQ-01, DQ-03

**Sources:**
- runtime: `python demo.py` (cwd `.ai/workflow/examples/scout-fixture`) / input: default config dict `{"value": 1}` mutated to `2` mid-run / observed result: stdout `initial=1`, `configured=2`, `actual=1` / exit status: 0

**Method:** execution

**Scope:** Single run on the observed snapshot.

### F-03 [FACT]

**Statement:** No module in the fixture defines or calls any reload-like method (`reload`, `update`, `refresh`, `invalidate`); adding `reload()` cannot duplicate existing behavior inside the fixture.

**Questions:** DQ-02

**Sources:**
- negative search: scope `.ai/workflow/examples/scout-fixture/*.py` for identifiers `reload|update|refresh|invalidate` / exclusions: none / result: no matches

**Method:** static

**Scope:** Fixture directory only; adopting repositories may define their own callers.

### F-04 [UNKNOWN]

**Statement:** Whether re-reading the whole dict on `reload()` is required, or re-reading only the `"value"` key is sufficient, is undetermined.

**Questions:** DQ-01

**Sources:**
- UNKNOWN: the intended `reload()` contract (whole-config freshness vs single-key re-read) / collect at: senior decision on the intended contract (see U-01)

**Method:** unknown

**Scope:** Open by design; see Unknowns U-01.

## Unknowns

- **U-01 / DQ-01, F-04 (critical):** the exact `reload()` semantics — partial key re-read vs whole-config re-validation. Impact: this decides the API contract and the acceptance criteria for the whole feature; every design alternative hinges on it. Next collection step: a senior decision (technical-decision role) on the intended contract; scouting cannot resolve an architectural preference. This unknown was escalated, not guessed.
- **U-02 / DQ-01:** whether external callers hold long-lived `CachedValue` instances. Impact: decides whether `reload()` must be added compatibly (additive-only) or may change construction semantics. Next collection step: search the consuming repository for `CachedValue(` constructions.

## Handoff

- **Established Fact IDs:** F-01, F-02, F-03
- **Decisions still required:** the `reload()` contract (U-01, escalated to a senior role); additive-only vs semantics-changing (U-02).
- **Missing evidence:** intended reload semantics; external construction sites.
- **Already investigated:** full fixture source; one runtime observation; scoped negative search for reload-like identifiers.
- **Stopping reason:** DQ-02 and DQ-03 are answered and DQ-01 is blocked on an architectural decision, not on more searching. Per the stop rules, the scout stopped and recorded the gap precisely instead of silently picking an API shape.

## Why this partial report cannot open the Gate

This report is ready for audit — its claims are anchored, its methods are
stated, and its gaps are precise. It is **not** sufficient evidence: DQ-01
carries a decision-changing UNKNOWN (U-01). Assigning every question a status
cannot alone open the Evidence Gate; only the evidence-auditor, by answering
the four sufficiency questions and recording the gate via `set-gate`, can
judge whether the remaining unknown can be explicitly shown not to affect the
selected decision. The scout records no verdict.
