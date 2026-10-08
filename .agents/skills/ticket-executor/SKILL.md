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

1. Read `.ai/work/<ticket-id>/state.yaml` first — it is authoritative. When
   entering without chat history, `ai-workflow resume <ticket-id>` prints the
   read-only continuation brief (PROTOCOL.md §"Portable continuation").
2. Confirm `next_action.role` is `ticket-executor`. If not, hand back.
3. Read the registered Plan referenced by `source_artifacts.plan` (a referenced
   source artifact, never a copy), plus `decision.md` and `evidence.md`.
   `progress.md` is the execution log, not a substitute for the Plan.
4. Record your working session:
   `ai-workflow claim <ticket-id> --harness <H> --model <M>`.
5. Execute exactly the current task named by `next_action.task` (its meaning is
   fixed by PROTOCOL.md §"Counter meaning"). Do not redesign; plan deviations
   go to escalation per `.ai/workflow/ESCALATION.md`.
6. When a task is done, record it with
   `ai-workflow complete-task <ticket-id>`.
   The command enforces the execution-readiness contract itself (PROTOCOL.md
   §"Registered execution readiness"): if the ticket is not ready it rejects
   the change and leaves the State untouched — fix the blocker or escalate,
   never force it.
7. Write `progress.md` per its template (`.ai/workflow/templates/progress.md`)
   and contract (`.ai/workflow/ARTIFACTS.md`): the task-granularity log of what
   you actually did, verified. Never copy the Plan's task contracts into it.
8. Commit per PROTOCOL.md §"Commits and rollback" and per-task granularity.
9. When all tasks are complete, write `handoff.md` (contract:
   `.ai/workflow/ARTIFACTS.md`) and report readiness for the `review`
   transition; otherwise write `handoff.md` before stopping.

## Repair path

After a `changes_requested` Review, `review -> implementation` returns the
ticket here (PROTOCOL.md §"Review and completion"): the rework tasks are
appended beyond the completed prefix and `next_action.task` names the first
appended one. Execute those tasks exactly as registered. Do not redesign — a
rework that needs a design or architectural change is escalated per
`.ai/workflow/ESCALATION.md`, not improvised.

Do not change `decision.md`; do not advance the phase (`ai-workflow advance` is
the checkpoint-handoff's job); do not invent work outside the current task.
