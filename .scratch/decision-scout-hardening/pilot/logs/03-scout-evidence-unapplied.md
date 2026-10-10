# Evidence — PAIR-01

Scout Report per `.ai/workflow/ARTIFACTS.md` (format_version 1). Collected by the round-1 scout session at the frozen starting revision.

## Metadata

```yaml
artifact_type: evidence
format_version: 1
ticket_id: PAIR-01
round: 1
observed_commit: 7e40f2b9de4bbdb4007b07a2578da1b68a708fcb
dirty_changes: [".ai/work/PAIR-01/state.yaml"]
created_at: "2026-10-10T01:42:33+00:00"
scout_harness: qoder-cli
scout_model: Qwen3.8-Flash
task_type: feature
report_status: ready-for-audit
```

## Decision Questions

### DQ-01

**Question:** Where do parsed values live, how long do they survive, and which ownership paths could accidentally couple two instances?

**Decision affected:** Feeds the technical decision on where reload state and cache ownership must sit so per-instance isolation (acceptance requirement 4) is guaranteed.

**Evidence targets:** config.py, cache.py (attribute ownership, construction paths).

**Answer:** ANSWERED

**Facts:** F-02, F-03, F-06, F-09

### DQ-02

**Question:** What observable parser/error behavior already exists, and what must be preserved when reload fails after some valid input has been consumed?

**Decision affected:** Feeds the decision on the reload failure contract: error type, propagation, and preservation of every previously cached value including lines parsed before the malformed one (acceptance requirement 3).

**Evidence targets:** cache.py parser and error paths, ValueCache.get, frozen test_behavior.py expectations.

**Answer:** ANSWERED

**Facts:** F-03, F-04, F-05, F-07, F-08, F-10

### DQ-03

**Question:** Which module boundary can support reload and independent verification without exposing mutable cache internals or broadening the public API?

**Decision affected:** The implementation seam (Config-level vs ValueCache-level vs new collaborator) — an architectural choice owned by the technical-decision role, not resolvable by more collection.

**Evidence targets:** config.py public surface, cache.py attribute visibility conventions, frozen API described by task.md.

**Answer:** UNKNOWN

**Facts:** F-01, F-02, F-03, F-08. The seam choice itself is a senior decision; per protocol this ambiguity is not answered by the Scout.

## Findings

### F-01 [FACT]

**Statement:** Config's starting API is exactly `__init__(path: str)` and `get(key: str) -> str`; no `reload` method or reload machinery exists in config.py or cache.py at the observed commit.

**Questions:** DQ-01, DQ-03

**Sources:**
- code: config.py:6-11 :: Config
- negative search: scope config.py and cache.py at 7e40f2b / exclusions: test_behavior.py, task.md, .ai/ / result: no occurrence of "reload" in either implementation file; the only mention in config scope is the module docstring at config.py:1; call sites exist only in test_behavior.py

**Method:** static

**Scope:** config.py and cache.py at commit 7e40f2b; does not cover any future change.

### F-02 [FACT]

**Statement:** Each `Config.__init__` constructs its own private `ValueCache(path)` instance in `self._cache`, and `get` delegates to that instance; there is no path-keyed registry, module-level store, or class attribute in either file.

**Questions:** DQ-01, DQ-03

**Sources:**
- code: config.py:3 :: import ValueCache
- code: config.py:7-8 :: Config.__init__
- code: config.py:10-11 :: Config.get

**Method:** static

**Scope:** observed starting fixture only; ownership of parsed data after construction is covered by F-03.

### F-03 [FACT]

**Statement:** Parsed values live in the instance attribute `ValueCache._values`, a plain dict that is assigned once at cache.py:20 only after the entire source file has been read and parsed into the function-local dict `values` (cache.py:7); the source path is retained per instance in `self._path` (cache.py:6).

**Questions:** DQ-01, DQ-02, DQ-03

**Sources:**
- code: cache.py:5-20 :: ValueCache.__init__
- code: cache.py:20 :: self._values
- code: cache.py:6 :: self._path

**Method:** static

**Scope:** the assignment order claim is control-flow reading of `__init__`; runtime confirmation was not possible (see F-10).

### F-04 [FACT]

**Statement:** The existing parser, for each stripped line: skips empty lines and lines starting with `#`; raises `ValueError("expected key=value")` on a line without `=`; splits on the first `=`; raises `ValueError("expected a nonempty key")` on an empty key; stores `values[key] = value.strip()`. Values are cached for the instance lifetime; nothing re-reads the file after construction.

**Questions:** DQ-02

**Sources:**
- code: cache.py:8-19 :: ValueCache.__init__
- code: cache.py:9-12 :: comment/blank skip
- code: cache.py:13-14 :: "expected key=value"
- code: cache.py:17-18 :: "expected a nonempty key"

**Method:** static

**Scope:** parsing behavior as written; error message texts are exact literals in the source.

### F-05 [FACT]

**Statement:** `ValueCache.get` is `return self._values[key]` — a missing key propagates `KeyError` with no default and no error translation; `Config.get` inherits that behavior via delegation.

**Questions:** DQ-02

**Sources:**
- code: cache.py:22-23 :: ValueCache.get
- code: config.py:10-11 :: Config.get

**Method:** static

**Scope:** existing `get` compatibility surface (acceptance requirement 5) as written.

### F-06 [INFERENCE]

**Statement:** The only paths by which two `Config` instances could couple are the per-instance `self._cache` and the per-instance `self._values` assigned at construction; because the parse accumulator is function-local and no shared store is keyed by path, a reload implementation that rebinds or mutates only `self`-scoped state cannot leak to another instance — coupling would require introducing shared state, not removing existing state.

**Questions:** DQ-01

**Sources:**
- inference basis: F-02, F-03

**Method:** inference

**Scope:** derived from the starting structure at 7e40f2b; the frozen tests (test_behavior.py:33-42, test_behavior.py:55-63) treat instance isolation under reload as the required observable.

### F-07 [INFERENCE]

**Statement:** Failure atomicity of the current parse is structural: because `self._values` is assigned only after the whole file parses successfully, any `ValueError` raised mid-parse leaves the previously assigned `self._values` untouched and discards only the function-local partial dict — so a reload that reuses this "parse fully into a local, then rebind at the end" shape preserves every previously cached value, including values parsed before the malformed line; a reload that instead assigns into `self._values` incrementally would corrupt it.

**Questions:** DQ-02

**Sources:**
- inference basis: F-03, F-04

**Method:** inference

**Scope:** control-flow claim about the existing pattern; not executed live (see F-10). Whether the malformed `__init__` raises before `self._values` exists (leaving a half-built object) is a separate construction-time detail; on a failed reload of an already-built instance, old values survive per this control flow.

### F-08 [FACT]

**Statement:** The frozen acceptance file pins the reload contract as observable requirements: `reload()` returns `None` (assertIsNone), values persist until an explicit reload, a valid reload exposes new values for that instance only, a malformed reload raises `ValueError` and preserves all previous values including ones parsed before the bad line, and two instances on the same path stay isolated.

**Questions:** DQ-02, DQ-03

**Sources:**
- code: test_behavior.py:10-63 :: ConfigBehaviorTest
- code: test_behavior.py:23-31 :: test_cached_until_reload
- code: test_behavior.py:33-42 :: test_reload_valid
- code: test_behavior.py:44-53 :: test_bad_reload_preserves_previous
- code: test_behavior.py:55-63 :: test_instances_isolated
- code: test_behavior.py:17-21 :: test_reads_initial

**Method:** static

**Scope:** test_behavior.py is protected/frozen per task.md; these are the acceptance targets, not implementation guidance.

### F-09 [FACT]

**Statement:** Evidence was collected against the frozen starting revision: HEAD was 7e40f2b9de4bbdb4007b07a2578da1b68a708fcb on branch pilot with a clean tree before the session, and at collection time the only dirty path is `.ai/work/PAIR-01/state.yaml` (written by the authorized claim mutation); config.py, cache.py, test_behavior.py and task.md are unmodified relative to HEAD.

**Questions:** DQ-01, DQ-02, DQ-03

**Sources:**
- runtime: ai-workflow resume PAIR-01 / input: ticket PAIR-01 / result: branch pilot, head 7e40f2b9de4b, "dirty : none", phase evidence_collection, next_action scout / exit: 0
- runtime: git rev-parse HEAD / input: none / result: 7e40f2b9de4bbdb4007b07a2578da1b68a708fcb / exit: 0
- runtime: git status --porcelain / input: none / result: single line "M .ai/work/PAIR-01/state.yaml" / exit: 0

**Method:** execution

**Scope:** snapshot at collection time in this session; later edits after this report are outside it.

### F-10 [UNKNOWN]

**Statement:** The live outcome of the five acceptance cases at the observed commit was not obtained: the acceptance command was refused by this session's tool-permission policy before execution, so the documented red baseline (read/isolation pass, three reload cases fail solely because `Config.reload` is missing) remains a preparation claim from task.md, not runtime evidence in this context.

**Questions:** DQ-02

**Sources:**
- unknown: exit status and per-case results of `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s . -p 'test_behavior.py' -v` at 7e40f2b / collect at: a session holding python3 test-execution permission (follow-up evidence round) or the auditor's own runtime access

**Method:** unknown

**Scope:** refusal was policy-level; per role instructions no retry or workaround was attempted. Static structure (F-01, F-08) makes AttributeError-on-reload the expected failure mode, but that expectation is unexecuted.

## Unknowns

- F-10 / DQ-02 live confirmation: the red-baseline runtime result is unobserved. Decision impact: the senior can rely on the static contract (F-01..F-08) plus task.md's documented preparation observation, or require a follow-up round with execution permission before deciding. Next collection step: rerun the acceptance command in a session where python3 execution is permitted.
- DQ-03 implementation seam: which module boundary carries `reload` is an architectural choice owned by technical_decision; it cannot be closed by more collection. Next step: the decision role reads F-01, F-02, F-03, F-08 and chooses.

## Handoff

- **Established Fact IDs:** F-01, F-02, F-03, F-04, F-05, F-08, F-09 (FACT); F-06, F-07 (INFERENCE from established facts); F-10 is an explicit UNKNOWN.
- **Decisions still required:** reload seam and cache-rebinding shape (DQ-03); whether the unexecuted red baseline (F-10) is acceptable for decision or requires a follow-up execution round.
- **Missing evidence:** one runtime item only — the acceptance command's per-case results and exit status at 7e40f2b.
- **Already investigated:** config.py, cache.py, test_behavior.py in full; task.md DQ-01/02/03 mapped to anchors; negative search for `reload` across implementation files; snapshot and dirty-path verification by execution.
- **Stopping reason:** all supplied questions are answered or are senior-owned by design; the single remaining gap (F-10) is unreachable in this context because test execution was policy-refused and role instructions forbid retry or workaround. Further static collection cannot change a decision.
