# Evidence — PAIR-01

The Evidence artifact is the Scout Report (see `.ai/workflow/ARTIFACTS.md` for
the full contract). Design proposals and the evidence verdict are forbidden.

## Metadata

```yaml
artifact_type: evidence
format_version: 1
ticket_id: PAIR-01
round: 1
observed_commit: f507bfa10b3920fbb52aed118686af8669c50926
dirty_changes: []
created_at: 2026-10-10T02:57:21+00:00
scout_harness: qoder-cli
scout_model: Qwen3.8-Flash
task_type: feature
report_status: ready-for-audit
```

## Decision Questions

DQ-01/02/03 are supplied by the frozen `task.md` (§"Decision Questions to
investigate"), quoted here as investigated. Each feeds the technical-decision
phase; the scout records observable facts, not the seam choice.

### DQ-01

**Question:** Where do parsed values live, how long do they survive, and which
ownership paths could accidentally couple two instances?

**Decision affected:** technical_decision — where the reloaded cache is stored
and how per-instance isolation is preserved across two `Config` objects on the
same path.

**Evidence targets:** `config.py` `Config.__init__` / `Config.get`; `cache.py`
`ValueCache.__init__` and `self._values`; `test_instances_isolated`.

**Answer:** ANSWERED

**Facts:** F-02, F-03, F-04

### DQ-02

**Question:** What observable parser/error behavior already exists, and what
must be preserved when reload fails after some valid input has been consumed?

**Decision affected:** technical_decision — a failure-safe `reload` must leave
every previously cached value intact when a mid-parse `ValueError` is raised.

**Evidence targets:** `cache.py` parse and raise paths; the deferred-commit
structure; `test_bad_reload_preserves_previous`; baseline run outcome.

**Answer:** ANSWERED

**Facts:** F-05, F-06, F-07, F-08

### DQ-03

**Question:** Which module boundary can support reload and independent
verification without exposing mutable cache internals or broadening the public
API?

**Decision affected:** technical_decision — selecting the reload seam (`Config`
vs `ValueCache`) and the public surface. The selection itself is an
architectural choice owned by the senior receiver, not answered here; the scout
establishes the candidate boundaries and their constraints.

**Evidence targets:** `Config` public methods and its `_cache` attribute;
`ValueCache` public methods and its `_values` attribute; the absence of any
`reload` symbol.

**Answer:** ANSWERED

**Facts:** F-01, F-03, F-04, F-07, F-09

## Findings

### F-01 [FACT]

**Statement:** `Config` exposes only `__init__(self, path: str)` and
`get(self, key: str) -> str`; it holds a single private `ValueCache` in
`self._cache` and delegates `get` to it.

**Questions:** DQ-01, DQ-03

**Sources:**
- code: config.py:7-8 :: Config.__init__
- code: config.py:10-11 :: Config.get

**Method:** static

**Scope:** At `observed_commit` f507bfa. Only these two methods are defined on
`Config`; no reload or cache-accessor is present.

### F-02 [FACT]

**Statement:** Parsed values live on the `ValueCache` instance as
`self._values`, a `dict` created fresh in `__init__` (local `values = {}`) and
committed at the end of construction; no class-level or module-level shared
store exists.

**Questions:** DQ-01

**Sources:**
- code: cache.py:7 :: ValueCache.__init__
- code: cache.py:20 :: ValueCache.__init__
- negative search: scope config.py and cache.py / exclusions: none / result: no module-level or class-level dict, registry, or cache variable defined in either file

**Method:** static

**Scope:** The two fixture modules under investigation only; does not rule out
coupling introduced by future reload code.

### F-03 [FACT]

**Statement:** Every `Config` constructs its own `ValueCache` instance from the
given path, so two `Config` objects on the same path own separate value dicts;
there is no path-keyed sharing in the current code.

**Questions:** DQ-01, DQ-03

**Sources:**
- code: config.py:8 :: Config.__init__
- code: cache.py:5-6 :: ValueCache.__init__

**Method:** static

**Scope:** Observed in the starting fixture; confirmed at runtime by
`test_instances_isolated` (F-04).

### F-04 [FACT]

**Statement:** Under the frozen baseline command, `test_reads_initial` and
`test_instances_isolated` pass; reading and per-instance isolation already work
without reload.

**Questions:** DQ-01, DQ-03

**Sources:**
- runtime: PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s . -p 'test_behavior.py' -v / input: test_reads_initial and test_instances_isolated / result: both reported ok in the verbose run / exit: 1

**Method:** test

**Scope:** One run of the acceptance command at observed_commit; exit 1 is the
whole-suite status (the three reload cases fail), not a per-case result.

### F-05 [FACT]

**Statement:** The parser strips each line, skips blank and `#`-prefixed
comment lines, raises `ValueError` on a line without `=` and on an empty key,
and accumulates `key -> value` (both sides stripped, split on the first `=`)
into a local dict.

**Questions:** DQ-02

**Sources:**
- code: cache.py:11-12 :: ValueCache.__init__
- code: cache.py:13-14 :: ValueCache.__init__
- code: cache.py:17-18 :: ValueCache.__init__
- code: cache.py:15-16 :: ValueCache.__init__
- code: cache.py:19 :: ValueCache.__init__

**Method:** static

**Scope:** The existing `ValueCache.__init__` parse rules; observable error
messages are the string literals at cache.py:14 and cache.py:18.

### F-06 [FACT]

**Statement:** Construction builds the value dict entirely in a local variable
and assigns it to `self._values` only after the whole line loop finishes
(cache.py:20); an error raised inside the loop therefore never leaves a
partially-built dict exposed as `self._values`.

**Questions:** DQ-02

**Sources:**
- code: cache.py:8-20 :: ValueCache.__init__

**Method:** static

**Scope:** Describes the current on-construction control flow only. Whether a
reload path reuses this deferred-commit shape is a design question, not observed
here.

### F-07 [FACT]

**Statement:** Under the frozen baseline command, `test_cached_until_reload`,
`test_reload_valid`, and `test_bad_reload_preserves_previous` all ERROR; each
traceback ends at an `AttributeError` because `Config.reload` does not exist.

**Questions:** DQ-02, DQ-03

**Sources:**
- runtime: PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s . -p 'test_behavior.py' -v / input: test_cached_until_reload at line 29, test_reload_valid at line 38, test_bad_reload_preserves_previous at line 48 / result: three ERROR, FAILED errors 3, AttributeError no attribute reload / exit: 1

**Method:** test

**Scope:** One baseline run at observed_commit; the errors occur at the first
`config.reload()` call in each test, before any reload semantics are exercised.

### F-08 [INFERENCE]

**Statement:** The missing `Config.reload` is the sole cause of the three
errors, not a parsing or isolation regression.

**Questions:** DQ-02, DQ-03

**Sources:**
- inference basis: F-04, F-07

**Method:** inference

**Scope:** The read and isolation cases pass (F-04) while the only failure mode
across the three erroring cases is the identical `AttributeError` on reload
(F-07); this matches the red baseline `task.md` predicts. Inference drawn from
one baseline run, not from running the reload code (which does not exist).

**Basis:** F-04, F-07

### F-09 [FACT]

**Statement:** No `reload` symbol or method is defined on either `Config` or
`ValueCache`; the feature is absent in the starting fixture, and
`ValueCache._values` is the private mutable store `get` reads from.

**Questions:** DQ-03

**Sources:**
- code: cache.py:22-23 :: ValueCache.get
- negative search: scope config.py and cache.py / exclusions: none / result: no reload identifier appears in either file

**Method:** static

**Scope:** The two fixture modules at observed_commit; establishing the feature
boundary for the seam decision, not proposing one.

## Unknowns

No missing repository facts within the scout's scope. The unresolved item is a
design choice, not an evidence gap:

- DQ-03 seam selection (where `reload` is implemented and whether it reuses the
  deferred-commit shape in F-06) is an architectural decision for the
  technical-decision role. Decision impact: it determines the reload error
  handling and instance-isolation approach. Next step: none for the scout — a
  follow-up collection round cannot resolve a design choice; it belongs to the
  technical_decision phase.

## Handoff

- **Established Fact IDs:** F-01 (Config surface + delegation), F-02 (values in
  per-instance `self._values`, no shared store), F-03 (per-instance
  `ValueCache` construction), F-04 (reads/isolation pass), F-05 (parse and
  error behavior), F-06 (deferred commit after full loop), F-07 (three reload
  cases error on missing `reload`), F-08 (errors are the missing method, not a
  regression), F-09 (no `reload` symbol exists).
- **Decisions still required:** which module boundary implements `reload` and
  how it preserves cached values on a mid-parse `ValueError` (technical_decision,
  senior-owned; not answerable by the scout).
- **Missing evidence:** none within scope. Reload behavior itself is
  unobservable because the method is not implemented (F-07, F-09).
- **Already investigated:** static reading of `config.py`, `cache.py`,
  `test_behavior.py`; negative searches for a shared store and for a `reload`
  symbol; one execution of the frozen baseline acceptance command.
- **Stopping reason:** All three supplied DQs have anchored FACT coverage and
  the red baseline is reproduced by an actually-executed command. Remaining
  open items are architectural decisions, not facts, so further collection
  cannot change a decision; the report is ready for evidence_audit.
