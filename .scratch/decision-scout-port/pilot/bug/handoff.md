# Handoff — PILOT-BUG-01

## What was done

Task 1 (the only registered task) is complete. `CachedValue` in `service.py` now
stores the caller's config mapping (`self._config = config`) in `__init__`, and
`read()` returns `self._config["value"]`, removing the copy-at-construction that
caused the stale read. `python demo.py` now prints `initial=1`, `configured=2`,
`actual=2` and exits 0. All registered tasks are complete; state is ready for the
`review` transition.

## What remains

Nothing for implementation. The `review` transition is owned by checkpoint-handoff
and must not be advanced from here.

## Important discoveries

- The v2 evidence gate is byte-bound to `.ai/work/PILOT-BUG-01/evidence-audit.md`:
  do NOT run `git checkout` / `git restore` / branch switches before review
  completes — they rewrite the file's line endings and make the gate stale.
- Only `service.py` needed to change; `demo.py` is the sole consumer (F-04) and was
  not touched.

## Artifact identity

- Evidence: .ai/work/PILOT-BUG-01/evidence.md sha256 71855e12d011d2d7345577633af211ae15e801b7e2b7e7056d8385dd9ab3a3f2 observed_commit b5a13a883095151d53f69992345003267a828a9f round 1
- Evidence audit: .ai/work/PILOT-BUG-01/evidence-audit.md sha256 544977b162351a3a0114c079dc4904a29fdc736fe8141ed0fafaa9c12213439c gate sufficient
- Decision: .ai/work/PILOT-BUG-01/decision.md sha256 c7cf43888718f638c1af0972fd7f358baed48a7139bd45b9aee24f144803fdb2
- Plan: .scratch/PILOT-BUG-01/plan.md sha256 67a62c313ba78db8013d03b1a8dd1e804d44d9580cf2db04ad958ee33a0b152c (registered)
- Review: .ai/work/PILOT-BUG-01/review.md (missing) verdict none

## Verification limits

Verified by execution: `python demo.py` on this worktree produced the expected
stdout and exit status 0. Not verified: no other Python version or platform was
tested; no callers outside this repository exist in-repo (F-04), and out-of-repo
snapshot-semantics callers are out of scope for this bug.

## Known relevant drift

- Repository HEAD: bc290efeac531ef5a5da3e0e0654f85154bbb036 (pre-task-1 commit)
- Evidence observed commit: b5a13a883095151d53f69992345003267a828a9f — differs from
  HEAD; the affected anchors were relevance-assessed during the audit and the gate
  is sufficient (recorded facts were not discarded).
- Review reviewed commit / verdict: none / pending
- Changed paths that matter: service.py

## Current failure (if any)

None.

## Do not repeat

- Do not re-read the bug or re-derive the cause: F-01/F-03 already establish
  copy-at-construction as the cause; the fix is done and verified.
- Do not modify `demo.py`, the constructor signature, or the `read()` return type.
- Do not add imports or new modules.

## Next recommended action

Per state.yaml: all tasks complete — `checkpoint-handoff` should perform the
`review` transition (role `reviewer`). No blockers.

## Repository State

- Branch: pilot/bug
- HEAD: bc290efeac531ef5a5da3e0e0654f85154bbb036
- Uncommitted files: service.py, .ai/work/PILOT-BUG-01/progress.md, .ai/work/PILOT-BUG-01/handoff.md, .ai/work/PILOT-BUG-01/state.yaml (this task's commit)
- Test status: passing (python demo.py → initial=1, configured=2, actual=2, exit 0)
