---
name: checkpoint-handoff
description: Verify state consistency, perform phase transitions, and write handoff.md. Any model tier. Use when a ticket's next_action.role is "checkpoint-handoff" or when a phase transition or handoff is due.
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
4. Verify state consistency before any transition: the phase change must be an
   allowed transition, `evidence.gate` must satisfy the gate rule for the
   destination phase, and required artifacts must exist. If a transition is
   illegal, do not perform it; escalate.
5. Perform the allowed transition by updating `phase` (and, where required,
   `evidence.gate`) in state.yaml, then set the destination role in
   `next_action`. Clear `escalation.required` only if a senior resolved it per
   `.ai/workflow/ESCALATION.md`. Set `claim` before work, update `provenance`.
6. Write `handoff.md` per the contract in `.ai/workflow/ARTIFACTS.md`: the
   fixed sections plus the Repository State block (branch, HEAD, uncommitted
   files, test status). No unverified claims.
7. Ensure validate-clean before handoff: run the workflow validator; no ERROR
   findings may remain. Record any WARN findings in handoff.md.
8. Commit per the protocol's commit discipline (phase-boundary commit).

At `done`, clear `next_action` in state.yaml.
