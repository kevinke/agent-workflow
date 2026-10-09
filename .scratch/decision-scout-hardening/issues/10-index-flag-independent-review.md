# 10: Review drift independent of Git index hints

Ticket ID: HARDEN-010
Type: task
Status: planned — awaiting plan review and execution method
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

- [ ] Both flags and their combination cannot hide edited/deleted source,
      tests/fixtures or the registered Plan from either `set-review` verdict.
- [ ] A previously recorded verdict becomes stale in validate/resume and
      blocks done/export after the same flagged edit. Refused export leaves
      no output or partial file.
- [ ] Present unchanged flagged files are accepted; the exact existing
      Ticket-record exemptions and relevant untracked-path rules are retained.
- [ ] Absent skip-worktree paths, including actual sparse-checkout absence,
      produce drift or a named assessment blocker without materializing files.
- [ ] Combined equal-size/cached-mtime collision remains detected after flag
      handling rewrites the disposable index; no sleeps or retry-to-green.
- [ ] Read-only checks/rejected mutations preserve real index bytes, flags and
      nanosecond mtime, State, artifacts and a pre-existing real index.lock.
      Assessment failures cannot fall back to the real index or silently pass.
- [ ] Public-command regressions fail before the fix and pass afterward;
      the complete existing unittest suite and v1 compatibility pass.

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
