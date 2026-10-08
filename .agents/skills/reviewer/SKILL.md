---
name: reviewer
description: Independently review the current change against the registered Plan and decision.md, record the verdict with ai-workflow set-review, and write review.md during review. Senior default in an independent context. Use when a ticket's next_action.role is "reviewer" or when a Review verdict must be recorded.
---

# reviewer

A thin operational procedure. All business rules live in the protocol under
`.ai/workflow/`; read those files before acting. Do not restate protocol rules here.

## Phase scope

`review` (see `.ai/workflow/ROLES.md`). Senior default; review in an independent
context, not the context that wrote the change.

## Procedure

1. Read `.ai/work/<ticket-id>/state.yaml` first — it is authoritative. When
   entering without chat history, `ai-workflow resume <ticket-id>` prints the
   read-only continuation brief (PROTOCOL.md §"Portable continuation").
2. Confirm `next_action.role` is `reviewer`. If not, hand back.
3. Read `.ai/workflow/ARTIFACTS.md` for the review contract and
   `.ai/workflow/PROTOCOL.md` (§"Review and completion") for the review, repair,
   and completion rules.
4. Read the registered Plan (referenced by `source_artifacts.plan`, never a
   copy) and `decision.md` (by reference). These are the contract under review.
5. Independently verify the acceptance criteria against the actual change and
   the recorded verification results — do not trust the change's own summary.
   Read the code, tests, and evidence the task claims.
6. Record your working session:
   `ai-workflow claim <ticket-id> --harness <H> --model <M>`.
7. Write `review.md` per the contract in `.ai/workflow/ARTIFACTS.md` — that
   contract owns the required Metadata, the required sections, and what is
   forbidden. Follow it exactly.
8. Record the verdict:
   `ai-workflow set-review <ticket-id> --verdict <pass|changes_requested>`.
   The recorded verdict is bound to the Review artifact, the reviewed commit,
   and the registered Plan (`.ai/workflow/ARTIFACTS.md` §review.md;
   `.ai/workflow/STATE_SCHEMA.md` §"v2 Review binding"); follow those contracts
   for staleness and re-review conditions.
9. On `changes_requested`, the rework path is append-only (PROTOCOL.md
   §"Review and completion"): the senior registers an appending Plan and the
   ticket returns to `implementation`. Local repairs stay within the recorded
   decision; design or architecture changes escalate per
   `.ai/workflow/ESCALATION.md` — they are not improvised here.
10. Do not advance the phase yourself; the checkpoint-handoff performs the
    transitions (`review -> done`, the repair path), which the protocol gates
    on the recorded verdict.
11. Write `handoff.md` per the contract in `.ai/workflow/ARTIFACTS.md` before
    stopping.
12. Commit per PROTOCOL.md §"Commits and rollback".

Do not write production code or `decision.md`; do not advance the phase — the
transition belongs to the checkpoint-handoff via `ai-workflow advance`.
