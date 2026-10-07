---
name: ticket-executor
description: Execute one bounded implementation task from the plan, record progress with ai-workflow complete-task, write progress.md, and commit. Cheap-model role. Use when a ticket's next_action.role is "ticket-executor" during implementation.
---

# ticket-executor

A thin operational procedure. All business rules live in the protocol under
`.ai/workflow/`; read those files before acting. Do not restate protocol rules here.

## Phase scope

`implementation` (bounded) (see `.ai/workflow/ROLES.md`). Cheap-model role.

## Procedure

1. Read `.ai/work/<ticket-id>/state.yaml` first — it is authoritative.
2. Confirm `next_action.role` is `ticket-executor`. If not, hand back.
3. Read the registered Plan referenced by `source_artifacts.plan` (a referenced
   source artifact, never a copy), plus `decision.md` and `evidence.md`.
   `progress.md` is the execution log, not a substitute for the Plan.
4. Record your working session:
   `ai-workflow claim <ticket-id> --harness <H> --model <M>`.
5. Execute exactly the current task named by `next_action.task` (the completed
   count plus one). Do not redesign; plan deviations go to escalation per
   `.ai/workflow/ESCALATION.md`.
6. When a task is done, record it with
   `ai-workflow complete-task <ticket-id>`. On a `workflow_version: 2` Ticket a
   registered, unchanged Plan is required and `--total N` cannot override the
   registered count; if the ticket is not ready the command rejects the change
   and leaves the State untouched.
7. Write `progress.md` per the contract in `.ai/workflow/templates/progress.md`:
   for the completed task, the actual changes, the verification and its observed
   result, any deviation from the plan, and unresolved problems. Never copy the
   Plan's task contracts; not every shell command.
8. Commit per the protocol's commit discipline and per-task granularity.
9. When all tasks are complete, write `handoff.md` and report readiness for
   the `review` transition; otherwise write `handoff.md` before stopping.

## Repair path

After a `changes_requested` Review, `review -> implementation` returns the
ticket here with the reviewer's rework registered as tasks appended beyond the
completed prefix (`next_action.task` is the first appended task). Execute those
appended tasks exactly as registered — the failed verdict is cleared to
`pending` and the completed tasks are preserved, so do not redo or renumber
them. Do not redesign: a rework that needs a design or architectural change is
escalated per `.ai/workflow/ESCALATION.md`, not improvised.

Do not change `decision.md`; do not advance the phase (`ai-workflow advance` is
the checkpoint-handoff's job); do not invent work outside the current task.
