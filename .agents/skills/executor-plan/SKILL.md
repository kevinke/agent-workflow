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
5. Write the implementation plan as `plan.md`: ordered `Task N` sections, each
   with objective, Fact/decision inputs, allowed and protected scope,
   invariants, acceptance criteria, verification, dependencies, and escalation
   conditions (see `.ai/workflow/ARTIFACTS.md`).
6. Register the plan on a `workflow_version: 2` Ticket:
   `ai-workflow register-plan <ticket-id> --path <plan> --total N`.
   Registration stores the reference and its hash plus the ordered task hashes
   without counting any task complete. On a v1 Ticket skip this step and record
   the task count in `progress.md` instead.
7. Advance:
   `ai-workflow advance <ticket-id> --to implementation`.
   The `ticket-executor` marks tasks complete
   (`ai-workflow complete-task <ticket-id>`); you do not pre-set the counters.
8. Write `handoff.md` before stopping (fixed sections + Repository State block).
9. Commit per the protocol's commit discipline (phase-boundary commit).

Do not implement the plan yourself; implementation belongs to the
`ticket-executor` role.
