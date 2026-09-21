---
name: ticket-executor
description: Execute one bounded implementation task from the plan, then update state.yaml, progress.md, and commit. Cheap-model role. Use when a ticket's next_action.role is "ticket-executor" during implementation.
---

# ticket-executor

A thin operational procedure. All business rules live in the protocol under
`.ai/workflow/`; read those files before acting. Do not restate protocol rules here.

## Phase scope

`implementation` (bounded) (see `.ai/workflow/ROLES.md`). Cheap-model role.

## Procedure

1. Read `.ai/work/<ticket-id>/state.yaml` first — it is authoritative.
2. Confirm `next_action.role` is `ticket-executor`. If not, hand back.
3. Read the plan (from `source_artifacts.plan`), `decision.md`, and `evidence.md`.
4. Execute exactly the current task (`implementation.current_task`). Do not
   redesign; plan deviations go to escalation per `.ai/workflow/ESCALATION.md`.
5. Update `implementation` in `state.yaml`: append the completed task to
   `completed_tasks`, advance `current_task` (or signal completion of all
   tasks). Set `claim` before work, update `provenance`.
6. Write `progress.md` per the contract in `.ai/workflow/ARTIFACTS.md`:
   completed task, files changed, tests run, deviation from plan, open issues.
   Not every shell command.
7. Commit with the commit prefix and per-task granularity defined in the
   protocol's commit discipline.
8. When all tasks are complete, write `handoff.md` and report readiness for
   the `review` transition; otherwise write `handoff.md` before stopping.

Do not change `decision.md`; do not advance the phase yourself; do not invent
work outside the current task.
