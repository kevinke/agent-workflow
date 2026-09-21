---
name: executor-plan
description: Write the implementation plan from decision.md and advance a ticket to implementation during planning. Senior-model role only. Use when a ticket's next_action.role is "executor-plan".
---

# executor-plan

A thin operational procedure. All business rules live in the protocol under
`.ai/workflow/`; read those files before acting. Do not restate protocol rules here.

## Phase scope

`planning` (see `.ai/workflow/ROLES.md`). Senior-model role only.

## Procedure

1. Read `.ai/work/<ticket-id>/state.yaml` first — it is authoritative.
2. Confirm `next_action.role` is `executor-plan`. If not, hand back.
3. Read `decision.md` (the source of the plan).
4. Write the implementation plan: an ordered decomposition of the decision into
   concrete tasks, each executable by a cheap model within a bounded step.
5. Reference the plan by path in `source_artifacts.plan`; never copy the plan
   body into `.ai/` (the protocol integrates plans by reference).
6. Update `state.yaml`: advance `phase` to `implementation`, set
   `implementation.total_tasks` to the plan's task count, set `current_task`
   to the first task, and point `next_action` at the `ticket-executor` role.
   Set `claim` before work, update `provenance`.
7. Write `handoff.md` before stopping (fixed sections + Repository State block).
8. Commit per the protocol's commit discipline (phase-boundary commit).

Do not implement the plan yourself; implementation belongs to the
`ticket-executor` role.
