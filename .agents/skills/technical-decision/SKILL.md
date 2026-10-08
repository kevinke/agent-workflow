---
name: technical-decision
description: Write decision.md and advance a ticket to planning with ai-workflow advance during technical_decision. Senior-model role only. Use when a ticket's next_action.role is "technical-decision" and evidence.gate is sufficient.
---

# technical-decision

A thin operational procedure. All business rules live in the protocol under
`.ai/workflow/`; read those files before acting. Do not restate protocol rules here.

## Phase scope

`technical_decision` (see `.ai/workflow/ROLES.md`). Senior-model role only.

## Procedure

1. Read `.ai/work/<ticket-id>/state.yaml` first — it is authoritative. When
   entering without chat history, `ai-workflow resume <ticket-id>` prints the
   read-only continuation brief (PROTOCOL.md §"Portable continuation").
2. Confirm `next_action.role` is `technical-decision` and `evidence.gate` is
   `sufficient`. If either fails, do not act; escalate per
   `.ai/workflow/ESCALATION.md`.
3. Read `evidence.md` and `evidence-audit.md`.
4. Record your working session:
   `ai-workflow claim <ticket-id> --harness <H> --model <M>`.
5. Write `decision.md` per the contract in `.ai/workflow/ARTIFACTS.md` — that
   contract owns the required content set and the forbidden content. Follow it
   exactly; leave nothing undecided that the plan needs.
6. Advance:
   `ai-workflow advance <ticket-id> --to planning`.
   The command enforces the gate and points `next_action` at the
   `executor-plan` role. If it is rejected, the state is not ready — fix it,
   do not force the transition.
7. Write `handoff.md` per the contract in `.ai/workflow/ARTIFACTS.md` before
   stopping.
8. Commit per PROTOCOL.md §"Commits and rollback" (phase-boundary commit).

If the decision depends on missing information, escalate per
`.ai/workflow/ESCALATION.md` rather than guess.
