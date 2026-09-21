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
3. Read the plan (from `source_artifacts.plan` or `progress.md`), `decision.md`,
   and `evidence.md`.
4. Record your working session:
   `ai-workflow claim <ticket-id> --harness <H> --model <M>`.
5. Execute exactly the current task (`implementation.current_task`). Do not
   redesign; plan deviations go to escalation per `.ai/workflow/ESCALATION.md`.
6. When a task is done, record it:
   `ai-workflow complete-task <ticket-id> [--total N]`.
   Pass `--total N` on the first task to set the plan's task count; afterwards
   the command increments `current_task` and appends to `completed_tasks`.
7. Write `progress.md` per the contract in `.ai/workflow/ARTIFACTS.md`:
   completed task, files changed, tests run, deviation from plan, open issues.
   Not every shell command.
8. Commit per the protocol's commit discipline and per-task granularity.
9. When all tasks are complete, write `handoff.md` and report readiness for
   the `review` transition; otherwise write `handoff.md` before stopping.

Do not change `decision.md`; do not advance the phase (`ai-workflow advance` is
the checkpoint-handoff's job); do not invent work outside the current task.
