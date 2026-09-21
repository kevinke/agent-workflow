---
name: checkpoint-handoff
description: Verify state consistency, perform phase transitions with ai-workflow advance, and write handoff.md. Any model tier. Use when a ticket's next_action.role is "checkpoint-handoff" or when a phase transition or handoff is due.
---

# checkpoint-handoff

A thin operational procedure. All business rules live in the protocol under
`.ai/workflow/`; read those files before acting. Do not restate protocol rules here.

## Phase scope

Phase transitions and handoff (see `.ai/workflow/ROLES.md`). Any model tier.

## Procedure

1. Read `.ai/work/<ticket-id>/state.yaml` first — it is authoritative.
2. Confirm `next_action.role` is `checkpoint-handoff`. If not, hand back.
3. Read `.ai/workflow/PROTOCOL.md` (state machine, handoff discipline) and
   `.ai/workflow/STATE_SCHEMA.md` (allowed transitions).
4. Run `ai-workflow validate <ticket-id>` first — it must report no ERROR
   findings. Record any WARN findings in handoff.md.
5. Record your working session:
   `ai-workflow claim <ticket-id> --harness <H> --model <M>`.
6. Perform the transition:
   `ai-workflow advance <ticket-id> --to <destination>`.
   The command enforces the allowed transition and the evidence gate, points
   `next_action` at the destination phase's role, and clears `next_action` at
   `done`. If it rejects the transition, the state is not ready — do not force
   it; fix the blocker or escalate.
7. Clear `escalation.required` only if a senior resolved it per
   `.ai/workflow/ESCALATION.md`:
   `ai-workflow escalate <ticket-id> --clear`.
8. Write `handoff.md` per the contract in `.ai/workflow/ARTIFACTS.md`: the
   fixed sections plus the Repository State block (branch, HEAD, uncommitted
   files, test status). No unverified claims.
9. Commit per the protocol's commit discipline (phase-boundary commit).
