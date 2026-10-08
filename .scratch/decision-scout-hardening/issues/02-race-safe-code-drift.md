# 02: Race-safe read-only dirty-code detection

Ticket ID: HARDEN-002
Type: task
Status: implemented — integration evidence recorded 2026-10-09
Blocked by: None
Parent: [supplemental spec](../spec.md#c2--race-safe-read-only-code-drift-harden-002)
Source findings: S-02; [disposition](../review-disposition.md)
Plan: [development plan](../../../docs/superpowers/plans/2026-10-08-harden-02.md)

## What to build

Equal-size dirty code cannot retain a Review pass, and the receiving read leaves the real Git index untouched.

## Scope and ownership

Own the complete C2 outcome from contract/documentation through public-command behavior and its regression or manual evidence. Exact files and interfaces are frozen in the linked plan. Honor its write set; other work may share mutation/validation files, so do not revert unrelated changes and schedule one writer for overlapping files. This issue is pending implementation; original SCOUT tickets stay historical.

## Acceptance criteria

- [x] A deterministic timestamp-collision regression detects the dirty fixture without sleeping or retrying.
- [x] set-review and done reject the dirty snapshot; resume/validate show relevant drift.
- [x] Staged, unstaged, untracked and deleted relevant files remain covered; workflow-only exclusions keep their existing scope.
- [x] Original index bytes/mtime, State and artifacts are unchanged by all read-only checks, including an existing index lock.
- [x] Run focused regressions and the integration suite; document the original intermittent failure and its deterministic replacement.

## Verification

Use the linked plan's named cases and commands. Negative mutations preserve State bytes; read-only operations preserve artifacts and Git index. HARDEN-009 has manual live acceptance and is not completed by automated fixtures. Global compatibility constraints in the supplemental spec apply to every slice.

## Escalation conditions

If implementation requires changing v2 digest semantics, completed task history, acceptance boundaries or dependencies beyond the linked contract, record the conflict before proceeding. Do not silently widen the slice or infer model-session budget from this planning request.

## Comments

- 2026-10-08 — Created from the post-implementation review at the user's request; ready for development planning/execution, not a resolved finding.
- 2026-10-09 — Implemented by 8a0b92b (stat-preserving `copy2` index copy); independently reviewed. Integration evidence: full-suite run at 3cef3db — `ReviewV2Test.test_racy_equal_size_edit_is_detected_read_only`, `test_drift_path_classes_stay_relevant` (staged/unstaged/untracked/deleted/workflow-only matrix) and `test_racy_drift_with_real_index_lock` passed, including the read-only index bytes/mtime assertions. `test_racy_edit_blocks_done_and_resume` FAILED IN FIXTURE SETUP before any production code ran: `_racy_edit` backdates the file mtime with `os.utime(ns=...)` (tests/test_review_v2.py), but the following `git add` process observed the file's earlier fixture-write mtime (index cached `…7313:708224000` where `…7313:000000000` was requested), so the determinism precondition at line 258 fired. Diagnosis: Windows cross-process mtime-visibility race, not a regression of the S-02 fix — the same helper passed four other times in this run, a 65-iteration standalone repro of the same sequence never reproduced it, and the production copy2 detection path passed in both `test_racy_equal_size_edit_is_detected_read_only` and `test_racy_drift_with_real_index_lock`. The original intermittent dirty-edit failure (copyfile losing cached-stat freshness) remains documented and its deterministic replacement (copy2 plus this fixture) stands. Boxes 2 and 5 stay unchecked until a run-of-record exercises the racy done/resume assertions; the suite was not rerun to get green.
- 2026-10-09 — Run of record: after fixture hardening 483a423 (`test_review_v2.py` only; scoped re-review passed — `_racy_edit` now captures the cached mtime from `git ls-files --debug` after the `git add` child fully exits and forces it onto both the file and the real index, with a bounded re-backdate loop), the full suite at 483a423 finished `Ran 399 tests in 372.617s` — `OK (skipped=2)`, exit 0, including `ReviewV2Test.test_racy_edit_blocks_done_and_resume`. Boxes 2 and 5 are checked on that deterministic green run; the fixture-race diagnosis above stands as the historical record of the intermittent failure and its deterministic replacement.
