# 01: Immutable and current Review bindings

Ticket ID: HARDEN-001
Type: task
Status: ready-for-agent
Blocked by: None
Parent: [supplemental spec](../spec.md#c1--immutable-current-review-identity-harden-001)
Source findings: S-01, S-09, ST-01; [disposition](../review-disposition.md)
Plan: [development plan](../../../docs/superpowers/plans/2026-10-08-harden-01.md)

## What to build

A receiver and completion gate agree on the exact immutable change reviewed, for both pass and changes_requested.

## Scope and ownership

Own the complete C1 outcome from contract/documentation through public-command behavior and its regression or manual evidence. Exact files and interfaces are frozen in the linked plan. Honor its write set; other work may share mutation/validation files, so do not revert unrelated changes and schedule one writer for overlapping files. This issue is pending implementation; original SCOUT tickets stay historical.

## Acceptance criteria

- [ ] Literal full/short object IDs resolve once to a full commit OID; HEAD/branch/tag names reject without State writes.
- [ ] Legacy symbolic bindings are surfaced as stale and require new review; no automatic authentication by resolving current HEAD.
- [ ] Changed Review bytes, relevant code/history and Plan block validate, resume and mutations for both recorded verdicts.
- [ ] Valid pending and appended changes_requested rework remain usable; completed task contracts stay unchanged.
- [ ] Current pass still permits workflow-only commits and done; v1 behavior is preserved.

## Verification

Use the linked plan's named cases and commands. Negative mutations preserve State bytes; read-only operations preserve artifacts and Git index. HARDEN-009 has manual live acceptance and is not completed by automated fixtures. Global compatibility constraints in the supplemental spec apply to every slice.

## Escalation conditions

If implementation requires changing v2 digest semantics, completed task history, acceptance boundaries or dependencies beyond the linked contract, record the conflict before proceeding. Do not silently widen the slice or infer model-session budget from this planning request.

## Comments

- 2026-10-08 — Created from the post-implementation review at the user's request; ready for development planning/execution, not a resolved finding.
