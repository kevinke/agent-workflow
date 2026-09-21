---
name: executor-plan
description: Write the implementation plan from decision.md and advance a ticket to implementation with ai-workflow advance during planning. Senior-model role only. Use when a ticket's next_action.role is "executor-plan".
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
4. Record your working session:
   `ai-workflow claim <ticket-id> --harness <H> --model <M>`.
5. Write the implementation plan: an ordered decomposition of the decision into
   concrete tasks, each executable by a cheap model within a bounded step.
   Record the plan in `progress.md` (or a referenced docs file), declaring the
   task count the executor will use.
6. Advance:
   `ai-workflow advance <ticket-id> --to implementation`.
   The `ticket-executor` sets the task counters when it completes the first
   task (`ai-workflow complete-task --total N`); you do not pre-set them.
7. Write `handoff.md` before stopping (fixed sections + Repository State block).
8. Commit per the protocol's commit discipline (phase-boundary commit).

Do not implement the plan yourself; implementation belongs to the
`ticket-executor` role.
