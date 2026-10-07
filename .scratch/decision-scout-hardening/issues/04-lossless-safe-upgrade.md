# 04: Lossless and malformed-safe explicit upgrade

Ticket ID: HARDEN-004
Type: task
Status: ready-for-agent
Blocked by: None
Parent: [supplemental spec](../spec.md#c4--lossless-explicit-upgrade-harden-004)
Source findings: S-07, S-08; [disposition](../review-disposition.md)
Plan: [development plan](../../../docs/superpowers/plans/2026-10-08-harden-04.md)

## What to build

Explicit conversion retains extension data and returns an actionable unchanged-input rejection for malformed supported State.

## Scope and ownership

Own the complete C4 outcome from contract/documentation through public-command behavior and its regression or manual evidence. Exact files and interfaces are frozen in the linked plan. Honor its write set; other work may share mutation/validation files, so do not revert unrelated changes and schedule one writer for overlapping files. This issue is pending implementation; original SCOUT tickets stay historical.

## Acceptance criteria

- [ ] Unknown keys survive in every existing nested map, including upgrade and extension maps.
- [ ] Malformed owned maps, counters and unsupported version/status/phase values are preflighted before any save.
- [ ] CLI failures return a normal error without Traceback and preserve exact input bytes.
- [ ] Already-v2 is byte-preserving; historical done v1 and unsupported conversion states remain rejected/preserved.
- [ ] Converted half-done work retains original phase, paused/blocked status and completion history without invented gates or Review.

## Verification

Use the linked plan's named cases and commands. Negative mutations preserve State bytes; read-only operations preserve artifacts and Git index. HARDEN-009 has manual live acceptance and is not completed by automated fixtures. Global compatibility constraints in the supplemental spec apply to every slice.

## Escalation conditions

If implementation requires changing v2 digest semantics, completed task history, acceptance boundaries or dependencies beyond the linked contract, record the conflict before proceeding. Do not silently widen the slice or infer model-session budget from this planning request.

## Comments

- 2026-10-08 — Created from the post-implementation review at the user's request; ready for development planning/execution, not a resolved finding.
