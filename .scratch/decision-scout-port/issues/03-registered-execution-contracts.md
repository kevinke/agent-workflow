# 03: Register bounded execution contracts and an explicit next task

Ticket ID: SCOUT-003
Type: task
Status: ready-for-agent
Blocked by: 02
Parent: [spec](../spec.md)
Plan: [Implementation plan](../../../docs/superpowers/plans/2026-10-07-scout-03.md)

## What to build

A senior planner hands an executor a referenced, structured Plan with a clear
current task. The CLI prevents missing or changed Plans and inconsistent task
counts from being treated as executable work.

## Scope and ownership

Own the execution contract/template, register-plan command, source reference
and hash, task routing, completion guards, planner/executor thin procedures,
schema descriptions, and CLI tests. The Plan remains a referenced source artifact
and Progress remains the execution log. Use v2 fixtures; release defaults stay v1.
Preserve the pre-existing counter-consistency implementation and tests.

## Acceptance criteria

- [ ] Ordered tasks declare objective, Fact/decision references, allowed and
  protected scope, invariants, acceptance, verification/expected results,
  dependencies, and escalation conditions; justified not-applicable is accepted.
- [ ] register-plan accepts source path and declared total, checks actual task
  count and contract structure, stores the path/hash, and initializes counters.
- [ ] Registration is limited to planning, documented senior escalation
  resolution, or appended rework in review. Unsupported contexts reject it.
- [ ] v2 planning-to-implementation rejects an unregistered, missing, incomplete,
  or drifted Plan and an unsafe Adoption Checkpoint when adoption applies.
- [ ] Initial next_action.task is 1. current_task means completed count; after
  completion next task is count plus one; after the final task no executable
  task remains. State and status output use the same meaning.
- [ ] complete-task requires implementation, current registered Plan and
  coherent counters. Optional total cannot override the registered count.
- [ ] Re-registration preserves completed task contracts and counter history;
  new rework is appended and remaining tasks are explicit. Rewrite of completed
  contracts is rejected.
- [ ] Progress requires task-level actual changes, verification/results,
  deviations, and unresolved problems; it does not duplicate the Plan.
- [ ] v1 remains compatible, unknown fields survive, and every rejection leaves
  State unchanged with an actionable error.

## Verification

Temporary-repo CLI scenarios: malformed tasks, absent Plan, declared-count
mismatch, source reference recording, initial/final task indices, changed Plan,
wrong-phase completion, registered-total override, counter divergence, appended
tasks, and rewritten completed contracts. Use acceptance-relevant execution
examples; do not assert that document structure proves implementation correctness.

## Escalation conditions

Open design decisions or changes to completed task meaning require senior
resolution. Executors must not repair missing design by rewriting the Plan.

## Context

Spec decision 4 and [R-02](../review-findings.md) describe this slice. Plan and
progress can be separated without copying existing user source documents.

## Comments

- 2026-10-07 — Bounded implementation contract follows trustworthy Evidence.
