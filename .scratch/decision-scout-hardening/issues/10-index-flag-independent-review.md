# 10: Review drift independent of Git index hints

Ticket ID: HARDEN-010
Type: task
Status: implemented and independently reviewed on branch `harden-010`; pending merge
Blocked by: None
Parent: [C2 index-flag follow-up](../spec.md#index-flag-follow-up-harden-010)
Source findings: S-10; [disposition](../review-disposition.md)
Plan: [development plan](../../../docs/superpowers/plans/2026-10-09-harden-10.md);
this Ticket is not a registered execution contract.

## What to build

Detect changed or deleted relevant tracked files despite `assume-unchanged`,
`skip-worktree` or both. Both Review verdicts and every consumer must agree on
currentness without changing the real index or losing racy-stat detection.

## Evidence and reproduction

In a disposable v2 Review fixture, change `src/feature.py` from `return 1` to
`return 9`: `set-review T1 --verdict pass` rejects. After
`git update-index --assume-unchanged src/feature.py`, the same command succeeds
and persists pass. `skip-worktree` also makes the shared `code_drift()` return
no problems. Clearing a flag in the copied index rewrites that copy's mtime;
the existing initial `copy2` alone cannot guarantee continued racy detection.
These are observed 2026-10-09 reproductions, not claims of a repaired runtime.

## Scope and ownership

Own `scripts/ai-workflow/review.py` drift assessment, relevant public-command
regressions in test_review_v2.py, test_resume_v2.py and test_artifact_archive.py,
and authoritative code-drift contract updates in STATE_SCHEMA.md/ARTIFACTS.md.
Retain `code_drift(root, ticket_id, reviewed_commit, plan_path) -> list[str]`.
Freeze an exact write set and algorithm during planning. Shared protocol files
require one writer at a time; preserve others' changes. No broad validation
rewrite, new state version, global Git settings or source reformatting.

## Acceptance criteria

- [x] Both flags and their combination cannot hide edited/deleted source,
      tests/fixtures or the registered Plan from either `set-review` verdict.
- [x] A previously recorded verdict becomes stale in validate/resume and
      blocks done/export after the same flagged edit. Refused export leaves
      no output or partial file.
- [x] Present unchanged flagged files are accepted; the exact existing
      Ticket-record exemptions and relevant untracked-path rules are retained.
- [x] Absent skip-worktree paths, including actual sparse-checkout absence,
      produce drift or a named assessment blocker without materializing files.
      Caveat: a true placeholder-directory sparse index (`core.sparseRepository`)
      was not constructible in these fixtures, so that one shape is unpinned.
- [x] Combined equal-size/cached-mtime collision remains detected after flag
      handling rewrites the disposable index; no sleeps or retry-to-green.
- [x] Read-only checks/rejected mutations preserve real index bytes, flags and
      nanosecond mtime, State, artifacts and a pre-existing real index.lock.
      Assessment failures cannot fall back to the real index or silently pass.
      Caveat closed during review: "preserve" originally did not cover a check
      that *creates* a new file, and one did (see Verification record).
- [x] Public-command regressions fail before the fix and pass afterward;
      the complete existing unittest suite and v1 compatibility pass.
      Caveat: two of the four rewritten Task 1 methods were inferred rather than
      re-demonstrated at RED; the seven Task 2 pins were demonstrated per-axis.

## Verification record

Implemented on branch `harden-010`: Task 1 `376e4b6`, Task 2 `487adb7` plus
`4830255`, whole-branch review fixes `48e2051`, and `a542486` correcting two
claims of mine that a re-review disproved. Full `unittest discover -v` at
`a542486`: `Ran 420 tests in 423.081s`, `OK (skipped=2)`, exit 0 — the two skips
remain the pre-existing symlink-privilege cases. Negative control at `86a823c`
(pre-Task 1) in a throwaway `--no-local` clone: all 39 subcases across the six
fix-dependent pins FAIL, covering each of `assume-unchanged`, `skip-worktree`
and both, edit and delete, both verdicts, on the Review, Resume and Archive
surfaces; the seventh pin (`test_clean_flagged_binding_still_accepted_by_consumers`)
correctly does not fail there because it is a no-false-positive guard, not a
fix-dependent one.

Two defects were found only by the whole-branch review, after three task-scoped
rounds, and both were reproduced before being fixed. Clearing hints by rewriting
*every* tracked path made `update-index` refuse an unmerged entry, so an ordinary
in-progress merge conflict turned all five consumers into an opaque `ContractError`
where the pre-ticket code reported correct drift; and honoring the repository's
`core.splitIndex` split the disposable copy, writing an orphan
`sharedindex.<oid>` into the real common dir from a check the contract calls
read-only. A base/shipped/fixed probe is retained in the plan's SDD workspace
(`final-fix-probe.log`), and both are now pinned by
`test_unmerged_index_still_assesses_drift` and
`test_assessment_creates_nothing_in_git_dir`. The reason no earlier pin caught
them is recorded as the real lesson: the read-only assertions compared a fixed
allow-list of index bytes, timestamps and flags, which cannot see a *new* file,
so the shared snapshot now compares the Git directory's file set.

## Known wording follow-up (not fixed here)

`mutate.py:687` and `review.py:289` prefix an assessment *blocker* with drift
language — "the reviewed code changed since <oid>: cannot establish currentness"
and "review is stale: cannot establish currentness" — for a case that is neither
changed nor stale. Every path still rejects and the blocker text names its own
remedy, so this is not a soundness defect, but these are the strings an agent
acts on. Fixing the prefix properly is outside this ticket's frozen write set
(`mutate.py` is not in it), so `STATE_SCHEMA.md` now instructs a reader to take
the named limitation over the prefix, and correcting the prefix itself is left
as a separate one-line change for whoever owns `mutate.py`'s message wording.

## Verification

Use disposable Git repositories and public commands; assert results, persisted
fields and byte preservation rather than exact error text. Run focused Review,
resume and archive suites, then the full `unittest discover` integration command.
Publish actual evidence; no model session or budget is required by these tests.

## Escalation conditions

Resolve sparse-index/platform limitations, Git comparison semantics or a need to
change existing exemptions at senior planning before implementation. A low-cost
executor must not invent the algorithm or bypass assessment errors.

## Comments

- 2026-10-09 — Created from the new reproduced P2 finding. Earlier HARDEN-002
  acceptance remains historical; this independent follow-up is not implemented.
- 2026-10-09 — Development plan saved with exact file ownership, interfaces,
  regression assertions and verification commands. Runtime acceptance remains
  pending; planning performs no implementation or model session.
