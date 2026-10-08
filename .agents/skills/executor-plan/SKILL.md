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

1. Read `.ai/work/<ticket-id>/state.yaml` first — it is authoritative. When
   entering without chat history, `ai-workflow resume <ticket-id>` prints the
   read-only continuation brief (PROTOCOL.md §"Portable continuation").
2. Confirm `next_action.role` is `executor-plan`. If not, hand back.
3. Read `decision.md` (the source of the plan).
4. Record your working session:
   `ai-workflow claim <ticket-id> --harness <H> --model <M>`.
5. Write the implementation plan as `plan.md` per the contract in
   `.ai/workflow/ARTIFACTS.md` — that contract owns the Metadata and the
   per-task section set. Follow it exactly.
6. On a `workflow_version: 2` Ticket, register the Plan:
   `ai-workflow register-plan <ticket-id> --path <plan> --total N`.
   Registration is v2-only (`.ai/workflow/STATE_SCHEMA.md` §"v2 Plan
   registration"); a v1 Ticket keeps its frozen v1 semantics (PROTOCOL.md
   §"Phases and statuses") and skips this step.
7. Advance:
   `ai-workflow advance <ticket-id> --to implementation`.
   The `ticket-executor` marks tasks complete
   (`ai-workflow complete-task <ticket-id>`); you do not pre-set the counters.
8. Write `handoff.md` per the contract in `.ai/workflow/ARTIFACTS.md` before
   stopping.
9. Commit per PROTOCOL.md §"Commits and rollback" (phase-boundary commit).

Do not implement the plan yourself; implementation belongs to the
`ticket-executor` role (see `.ai/workflow/ROLES.md`).
