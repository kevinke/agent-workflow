# Post-implementation review — 2026-10-08

Scope: `git diff 5ae8e27...00a3904`, including SCOUT-001..008, protocol,
production CLI, tests and pilot archives. Spec: [spec.md](spec.md).
Review method: code-review Skill, independent Standards/Spec reviews plus
primary-reviewer CLI reproductions.

No production changes, target checkout changes, commits or pushes were made.
The pre-existing working-tree differences were checked with
`git diff --ignore-space-at-eol --exit-code`: no substantive content differences.
They are line-ending differences; they were not reset.

## Verification evidence

- Primary full suite: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts/ai-workflow/tests -q`.
  **309 tests in 257.275s; one failure** in
  `ReviewV2Test.test_drift_variants_block_review_binding`, variant
  `_drift_dirty_edit`: expected rejection 1, received successful review binding 0.
- Independent Standards reviewer ran the same suite: 309 tests passed.
- Primary isolated rerun:
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts/ai-workflow/tests python3 -m unittest test_review_v2.ReviewV2Test.test_drift_variants_block_review_binding -v`:
  passed, 3.874s. This does not erase the full-run failure; S-02 below gives a
  controlled reproduction of dirty-change omission.
- Temporary-repository probes used existing `V2CLITestCase`/`ReviewV2Test`
  helpers and public CLI, unless explicitly described as the index experiment.
- Original pilot target was inspected without checkout or writes. `pilot/bug`
  resolves to `a1cbdab`, State done/pass; extracted code returns 2 after changing
  config. `pilot/feat` resolves to `aea68a6`, State done/pass; extracted code
  returns 5 then 7 after reload. This confirms those outcomes, not all workflow
  failure paths or comparative model efficiency.

## Standards

### ST-01 — Hard violation: mutable Review binding

[mutate.py:694](../../scripts/ai-workflow/mutate.py#L694) stores the input
`reviewed_commit` verbatim; [review.py:48](../../scripts/ai-workflow/review.py#L48)
resolves it on every check. This conflicts with CONTEXT's exact-revision Artifact
Binding and ARTIFACTS' current-review rule. Both the primary and independent
reviewer reproduced S-01 below. Persist an immutable resolved object ID.

### ST-02 — Hard violation: Skills restate Protocol business rules

ADR-0001 makes Skills thin adapters. Added report/resolution/review/rework rules
in `repo-scout/SKILL.md:25`, `checkpoint-handoff/SKILL.md:31`,
`ticket-executor/SKILL.md:24` and `reviewer/SKILL.md:24` duplicate the canonical
Protocol despite the Skills' own instruction not to restate it. Keep routing,
commands and authoritative section links there; maintain semantics in Protocol.

### ST-03 — Judgment: duplicated phase/artifact checks

`validate.py:374-405` and `validate.py:452-501` separately construct artifact
maps and phase requirements. This is a possible Duplicated Code smell, not a
language/tooling violation. Share the phase/artifact checks so validation and
reconstruction cannot diverge. Avoid a general framework.

Standards: three findings; the most consequential is ST-01. No additional
stdlib, restricted-parser or platform-standard breach was identified.

## Spec

### S-01 [P1] — A moving ref bypasses the current-review completion gate

Location: `scripts/ai-workflow/mutate.py:694-714`, `review.py:48-64`.
Requirement: spec decision 6, "Review-to-done requires current pass" and the
reviewed commit must identify the reviewed code.

Reproduction using a temporary fixture:

```python
t.prepare_v2_review()
t.write_review("pass", reviewed_commit="HEAD")
t.cli("set-review", "T1", "--verdict", "pass")  # exit 0
t.commit_code("src/feature.py", "def feature():\n    return 999\n")
t.cli("advance", "T1", "--to", "done")         # exit 0, phase done
```

The bound State contains literal `HEAD`; later drift computes HEAD..HEAD.
Branch refs have the same problem. Resolve/validate the revision at binding
time and store the full immutable object ID, with consistent Review metadata.
Add tests for HEAD and a branch moving after pass; retain short-ID compatibility
through explicit resolution if desired. The primary and independent reviewer
both confirmed this behavior.

### S-02 [P1] — Copying the index can hide dirty reviewed code

Location: `scripts/ai-workflow/review.py:110`.
Requirement: spec decision 6, "Require clean reviewed code"; dirty changes must
block verdict binding/completion while continuation observations remain read-only.

`shutil.copyfile` copies index bytes without its timestamp. Git's racy-stat
handling depends on that timestamp, so a byte-identical copy is not necessarily
an equivalent index for worktree freshness checks. The full suite observed a
dirty edit incorrectly receiving pass. A controlled temporary-repo experiment
used local `core.trustctime=false` and `core.checkstat=minimal`, an equal-size
1-to-3 return-value edit, and matching cached file stat times:

- Existing copied-index check returned `[]`; original-index `git diff` identified
  `src/feature.py`; original index bytes stayed unchanged.
- Holding index bytes constant and setting the copy's timestamp later returned
  `[]`; preserving original stat returned the changed source path.

This establishes the timestamp-dependent omission. Preserve the stat information
needed for Git's race detection, or deliberately refresh/invalidate stat caches
on the disposable index. Test same-size/coarse-time edits deterministically and
keep the real index read-only. Do not fix this by sleeping in tests.

### S-03 [P1] — Ordinary escalation and late-phase bootstrap cannot recover

Location: `scripts/ai-workflow/mutate.py:109`, `mutate.py:517`, `start.py:59`.
Requirement: spec: "Plan registration is allowed ... during recorded senior
escalation resolution"; changed Evidence/Plan use normal audit/registration paths.
SCOUT-007 also requires senior reconstruction at a retained phase.

Only `upgrade.requires_reconstruction` enables out-of-phase audit/registration.
From valid implementation, escalate and alter the Plan or Evidence:
`register-plan`/`set-gate` reject. Clearing the escalation does not permit them,
and `complete-task` still rejects drift. There is no public backward transition.

The independent reviewer also reproduced all four new v2 cases:
`start/adopt --phase implementation/review`. Each routes to workflow-bootstrap
but has no recovery marker; valid audit/Plan cannot be recorded. Confirming the
adoption checkpoint cannot unblock the missing contracts.

Introduce an explicit checked senior recovery mode covering ordinary escalation
and later-phase bootstrap, preserving completed task prefixes. Test recovery to
actual execution, not merely initial blocking/routing. ARTIFACTS' promise of
senior resolution and STATE_SCHEMA's upgrade-only limitation need reconciliation.

### S-04 [P2] — Ordinary escalation clear does not check restored readiness

Location: `scripts/ai-workflow/mutate.py:818-841`.
Requirement: spec says clear restores continuation "after checking validity".

The independent reviewer escalated a valid implementation Ticket, changed its
registered Plan and cleared with a referenced resolution. Clear returned 0 and
restored active/executor; immediate validate failed for Plan drift. Current-phase
checks run only for upgraded reconstruction. Check restored contracts for all
senior recovery paths, preserving paused/blocked Status and rejecting unchanged.

### S-05 [P1] — Committed archives lose seven of eight bound byte identities

Location: `pilot/report.md:14-16`, archived Evidence/Audit/Plan/Review files.
Requirement: portable persisted artifacts and source-linked, verifiable pilot
records. The report claims all archive bytes match their bound hashes.

Read-only SHA-256 comparison against archived State:

| Archive | File | Current file matches | HEAD Git blob matches |
|---|---|---|---|
| bug | evidence.md | yes | no |
| bug | evidence-audit.md | yes | no |
| bug | plan.md | yes | no |
| bug | review.md | yes | yes |
| feature | evidence.md | yes | no |
| feature | evidence-audit.md | yes | no |
| feature | plan.md | yes | no |
| feature | review.md | yes | no |

Git stores LF while working files include CRLF or mixed endings. No attributes
preserve the audit masks. A fresh clone with LF checkout cannot reproduce the
bound artifacts, and even a uniform CRLF checkout cannot preserve mixed masks.
Preserve exact archived bytes explicitly, e.g. binary snapshots/attributes plus
a hash manifest, and verify Git blobs or a fresh checkout before publishing.

Separately choose a portable gate identity strategy for future targets. Current
raw-byte hashing implements the written plan, but observed checkout rewrites
make it operationally unstable. Canonical line-ending hashing would need a
declared version/migration across audit, Plan and Review bindings; do not silently
reinterpret existing digests. This finding does not dispute the target's real
done/pass State: its current working bytes and results were verified.

### S-06 [P2] — Concrete structural requirements are not fully enforced

Location: `scripts/ai-workflow/contracts.py:487`, `:548`, `:553`, `:593`.
Requirement: spec decisions 2–3: file/line/symbol anchors, linked facts or
explicit unknown, non-placeholder metadata, matching audit round.

Six separate public-command probes all recorded a sufficient gate with exit 0:

1. `code: src/app.py :: main` (no line).
2. `code: src/app.py:1-2` (fixture has a named symbol but none supplied).
3. Sources replaced entirely by `trust me`.
4. An ANSWERED question's Facts replaced by `this was answered` (no Fact ID).
5. observed_commit replaced by `<pending>`.
6. Audit round set to `banana`, while Evidence/CLI round=1.

Presence-only fields and optional regex matches are not the required structure.
Validate the allowed source shapes, DQ/F links and field types/placeholders.
Audit's round comparison must reject nonintegers before comparing. Keep UNKNOWN
and justified file-scope cases legal; claim truth remains a separate review duty.
The shipped contract's "neither a line nor a symbol" wording is weaker than the
spec's anchor contract and should be reconciled.

### S-07 [P1] — Explicit upgrade deletes unknown nested fields

Location: `scripts/ai-workflow/upgrade.py:121-125`.
Requirement: spec decision 8: "Preserve ... unknown fields".

Independent reproduction: v1 State contains an `upgrade.custom_extension`;
`upgrade-ticket` exits 0 and replaces the whole map, deleting the extension.
Merge the three owned conversion fields into the existing map and test nested
unknown values. Existing tests cover unrelated root maps, not this collision.

### S-08 [P2] — Malformed but parseable upgrade input produces a traceback

Location: `scripts/ai-workflow/upgrade.py:117`.
Requirement: uninterpretable State stays unchanged "with a clear error".

Independent reproduction: v1 `evidence: malformed scalar` reaches `.get()` and
exits with AttributeError instead of UpgradeError. Bytes remain unchanged.
Check all required nested-map/counter shapes before conversion and translate
unsupported inputs to normal CLI errors. Do not broaden parser dependencies.

### S-09 [P2] — A stale failed Review is reported as valid

Location: `scripts/ai-workflow/validate.py:150-151`.
Requirement: SCOUT-005 says a bound Review edit needs a new verdict and validate
agrees with command-time checks.

Independent reproduction: bind changes_requested, edit review.md, then validate
returns 0/OK; repair correctly rejects its stale hash. Validate both recorded
verdicts' artifact/code identities. Allow the intentionally old Plan identity
during valid append-only repair, and keep truly pending Review valid.

Spec: nine findings. The primary completion blockers are S-01/S-02; recovery,
archive preservation and upgrade data preservation also need correction before
calling the complete workflow reliable. These are distinct from Standards.

## Follow-up observations, not additional correctness findings

- **Pilot scope:** report rows 150–151 label both Scout and senior audit/decision/
  Plan as DeepSeek-V4.1-Flash. This supports real cross-Harness independent review
  (the B logs confirm a fresh gpt-6.1-sol process), but does not separately
  demonstrate inexpensive Scout -> a distinct senior decision model. Supplement
  that pairing on a somewhat less trivial task; keep role and actual model
  identity separate. No monetary saving conclusion is justified; UNKNOWN
  telemetry and absent baseline are honestly documented.
- **Handoff placeholders:** detecting an unchanged scaffold is a syntactic check,
  not proving acceptance. Add phase-aware placeholder detection at handoff/review
  entry and completion; permit pending scaffolds early and justified None later.
  Prefer this narrow check over trying to judge natural-language truth.
- **Windows launch:** preserve the observed command/config guidance in a thin
  adapter runbook with an explicit diagnostic smoke check. The pilot documents
  one host-specific resolution; it is not evidence that the setting is universal.
- **Delivery order:** correct immutable review identity and dirty-code detection;
  implement recoverable senior resolution; preserve archive/upgrade data; tighten
  syntactic contracts and validation agreement; then supplement the paired-model
  pilot. Push/config consolidation alone would not address these defects.

These are review findings and proposed follow-up scopes, not implemented fixes
or newly claimed/resolved Tickets. Existing completed pilot Tickets were not
reopened or relabelled by this review.
