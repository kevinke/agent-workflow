# 02: Race-safe read-only dirty-code detection

Ticket ID: HARDEN-002
Type: task
Status: ready-for-agent
Blocked by: None
Parent: [supplemental spec](../spec.md#c2--race-safe-read-only-code-drift-harden-002)
Source findings: S-02; [disposition](../review-disposition.md)
Plan: [development plan](../../../docs/superpowers/plans/2026-10-08-harden-02.md)

## What to build

Equal-size dirty code cannot retain a Review pass, and the receiving read leaves the real Git index untouched.

## Scope and ownership

Own the complete C2 outcome from contract/documentation through public-command behavior and its regression or manual evidence. Exact files and interfaces are frozen in the linked plan. Honor its write set; other work may share mutation/validation files, so do not revert unrelated changes and schedule one writer for overlapping files. This issue is pending implementation; original SCOUT tickets stay historical.

## Acceptance criteria

- [ ] A deterministic timestamp-collision regression detects the dirty fixture without sleeping or retrying.
- [ ] set-review and done reject the dirty snapshot; resume/validate show relevant drift.
- [ ] Staged, unstaged, untracked and deleted relevant files remain covered; workflow-only exclusions keep their existing scope.
- [ ] Original index bytes/mtime, State and artifacts are unchanged by all read-only checks, including an existing index lock.
- [ ] Run focused regressions and the integration suite; document the original intermittent failure and its deterministic replacement.

## Verification

Use the linked plan's named cases and commands. Negative mutations preserve State bytes; read-only operations preserve artifacts and Git index. HARDEN-009 has manual live acceptance and is not completed by automated fixtures. Global compatibility constraints in the supplemental spec apply to every slice.

## Escalation conditions

If implementation requires changing v2 digest semantics, completed task history, acceptance boundaries or dependencies beyond the linked contract, record the conflict before proceeding. Do not silently widen the slice or infer model-session budget from this planning request.

## Comments

- 2026-10-08 — Created from the post-implementation review at the user's request; ready for development planning/execution, not a resolved finding.
