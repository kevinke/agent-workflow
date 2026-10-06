# 05: Require current review before completion and support explicit rework

Ticket ID: SCOUT-005
Type: task
Status: ready-for-agent
Blocked by: 03, 04
Parent: [spec](../spec.md)
Plan: [Implementation plan](../../../docs/superpowers/plans/2026-10-07-scout-05.md)

## What to build

A v2 Ticket can finish only after independent review of the current change and
Plan. A changes_requested verdict can send it back to implementation using
appended tasks, without losing completed work or silently changing the design.

## Scope and ownership

Own Reviewer role/Skill, Review contract/template, set-review command, review
binding/freshness checks, phase routing and repair edge, shared validation,
and end-to-end CLI tests. Keep checkpoint-handoff mechanical. Use v2 fixtures;
the shipped default remains v1 until 07.

## Acceptance criteria

- [ ] Entering review requires a registered current Plan, all tasks complete,
  coherent counters, required artifacts, and no unresolved escalation.
- [ ] Review routes to Reviewer, using an independent context and senior default;
  mechanical checkpoint-handoff alone cannot supply a technical verdict.
- [ ] Review artifact contains reviewed commit, Plan identity, acceptance
  results, verification commands/results, findings, verdict, and required rework.
- [ ] set-review records pass or changes_requested and binds it to artifact
  hash, reviewed commit, and Plan hash. Missing/placeholder artifact rejects it.
- [ ] done requires a current pass. Different/dirty code, tests or fixtures,
  changed Plan/Review, unrelated Git history, no verdict, or failed verdict block it.
- [ ] Workflow-only commits within this Ticket do not stale code review, while
  changing the bound Review artifact still needs a new verdict binding.
- [ ] review-to-implementation requires changes_requested and a registered Plan
  with appended rework; it preserves completed contracts/counters, clears pass,
  and chooses the first appended task.
- [ ] Architectural review findings use escalation; local repair stays within
  the decision. After repair, a new Review is required. done is not auto-reopened.
- [ ] validate and command-time checks agree; v1 remains compatible and
  rejections preserve State.

## Verification

Public-command temporary-repo lifecycle plus failures: incomplete tasks, absent
Review/verdict, code/test/fixture drift, dirty reviewed code, changed Plan/Review,
workflow-only commits, unrelated branch history, repeated changes_requested,
appended rework, re-review/pass/done, and no silent reopening. Check the repaired
[R-03](../review-findings.md) behavior rather than exact error wording.

## Escalation conditions

The CLI validates structural/snapshot conditions, not semantic reviewer quality.
Do not treat self-reported model tier as authentication or infer pass from tests
alone. Scope-changing repairs require senior resolution before execution.

## Comments

- 2026-10-07 — Completion gate and repair flow follow registered Plans and
  effective escalation, which are genuine blockers for this slice.
