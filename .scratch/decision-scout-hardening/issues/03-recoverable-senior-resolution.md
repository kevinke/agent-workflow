# 03: Recoverable senior resolution and late-phase bootstrap

Ticket ID: HARDEN-003
Type: task
Status: ready-for-agent
Blocked by: 01
Parent: [supplemental spec](../spec.md#c3--recoverable-senior-resolution-and-bootstrap-harden-003)
Source findings: S-03, S-04, ST-03; [disposition](../review-disposition.md)
Plan: [development plan](../../../docs/superpowers/plans/2026-10-08-harden-03.md)

## What to build

A senior can rebuild coherent retained-phase contracts through public commands, then restore the proper continuation without fabricating completed work.

## Scope and ownership

Own the complete C3 outcome from contract/documentation through public-command behavior and its regression or manual evidence. Exact files and interfaces are frozen in the linked plan. Honor its write set; other work may share mutation/validation files, so do not revert unrelated changes and schedule one writer for overlapping files. This issue is pending implementation; original SCOUT tickets stay historical.

## Acceptance criteria

- [ ] Ordinary unresolved escalation, explicit upgrade reconstruction and late-phase v2 bootstrap support bounded re-audit and Plan registration.
- [ ] New late-phase start/adopt creates explicit bootstrap recovery; existing half-ready v2 work can enter ordinary recovery via escalate.
- [ ] Routine execution stays blocked until a referenced resolution clears all retained-phase blockers atomically.
- [ ] Completed task hashes bind once when historically absent; subsequent registrations preserve the prefix and counters.
- [ ] Paused/blocked status and adoption checkpoints are preserved; pending Review and valid failed-review append recover without a deadlock.
- [ ] Validation and clear use one focused shared phase/artifact check implementation; no arbitrary phase jumps or broad validation rewrite.

## Verification

Use the linked plan's named cases and commands. Negative mutations preserve State bytes; read-only operations preserve artifacts and Git index. HARDEN-009 has manual live acceptance and is not completed by automated fixtures. Global compatibility constraints in the supplemental spec apply to every slice.

## Escalation conditions

If implementation requires changing v2 digest semantics, completed task history, acceptance boundaries or dependencies beyond the linked contract, record the conflict before proceeding. Do not silently widen the slice or infer model-session budget from this planning request.

## Comments

- 2026-10-08 — Created from the post-implementation review at the user's request; ready for development planning/execution, not a resolved finding.
