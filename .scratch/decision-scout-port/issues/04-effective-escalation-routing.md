# 04: Make escalation stop execution and select a senior resolver

Ticket ID: SCOUT-004
Type: task
Status: ready-for-agent
Blocked by: 02
Parent: [spec](../spec.md)
Plan: [Implementation plan](../../../docs/superpowers/plans/2026-10-07-scout-04.md)

## What to build

When a v2 Agent encounters decision-changing uncertainty, escalation actually
stops normal work and identifies the senior resolution step. Clearing it restores
a valid continuation without discarding an existing paused or blocked condition.

## Scope and ownership

Own escalation/clear and Status semantics, transition/completion blockers,
senior-resolution recording, route consistency validation, corresponding Protocol
and role instructions, and CLI regressions. Use v2 fixtures while default stays
v1. This slice has no dependency on Plan registration; it must accommodate that
slice when integrated and preserve other Agents' source edits.

## Acceptance criteria

- [ ] Escalate atomically stores scope/reason and original Status/action, sets
  escalation_required, and selects the resolver specified by spec decision 5.
- [ ] Human scope identifies the need for the user's answer rather than treating
  elapsed time or a machine guess as resolution.
- [ ] Routine advance and complete-task reject unresolved escalation. Setting
  active or editing an inconsistent route cannot pass validation or bypass it.
- [ ] V2 clear requires a nonempty --resolution describing senior resolution and
  supporting artifact references, and records it atomically. Human scope refers
  to the user's answer; absent resolution rejects clear. Required re-audit or
  Plan registration must be satisfied before restoring execution.
- [ ] Repeated escalation preserves original continuation. Clear checks and
  restores previous Status and current phase-appropriate action/task.
- [ ] Paused and blocked tickets retain those conditions after resolution.
- [ ] validate detects escalation/Status/route divergence and uses actionable
  errors. Rejected operations leave State unchanged.
- [ ] v1 remains compatible and no global model names, authentication promises,
  or filesystem locks are introduced.

## Verification

Reproduce [R-04](../review-findings.md) in a v2 fixture, then verify through public
commands: senior routing, completion/advance rejection, repeated escalation,
human scope, original pause/block restoration, missing resolution, invalid
continuation, and attempted Status bypass. Also keep the v1 path covered.

## Escalation conditions

If a resolution requires an arbitrary backward phase jump, stop and request
senior design work. Use the recorded resolution and normal artifact paths;
this Ticket does not add unconstrained phase resets.

## Comments

- 2026-10-07 — Repairs the demonstrated gap between escalation text and CLI.
