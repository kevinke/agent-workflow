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
   `.ai/workflow/STATE_SCHEMA.md` (phases and statuses).
4. Run `ai-workflow validate <ticket-id>` first — it must report no ERROR
   findings. Record any WARN findings in handoff.md.
5. Record your working session:
   `ai-workflow claim <ticket-id> --harness <H> --model <M>`.
6. Perform the transition:
   `ai-workflow advance <ticket-id> --to <destination>`.
   The command enforces the allowed transition and its gates (PROTOCOL.md
   §"Phases and statuses", §"Review and completion"). If it rejects the
   transition, the state is not ready — do not force it; fix the blocker or
   escalate.
7. Clear `escalation.required` only when a senior resolved it per
   `.ai/workflow/ESCALATION.md`:
   `ai-workflow escalate <ticket-id> --clear --resolution "<what was resolved
   and its supporting references>"`.
   (A v1 ticket keeps the bare `ai-workflow escalate <ticket-id> --clear`.)
8. Write `handoff.md` per the contract in `.ai/workflow/ARTIFACTS.md` — the
   fixed sections plus the Repository State block, as that contract defines
   them. No unverified claims.
9. Commit per PROTOCOL.md §"Commits and rollback" (phase-boundary commit).

## Continuing across sessions

When the previous session's chat is gone, run `ai-workflow resume <ticket-id>`:
it prints a read-only continuation brief (PROTOCOL.md §"Portable continuation").
Read it before acting; it never writes state. Model tiers are Harness-local
defaults (`.ai/workflow/ROLES.md`); if the tools or environment the brief
assumes are missing, escalate per `.ai/workflow/ESCALATION.md` rather than guess.

## Role boundary

This is a mechanical role: it performs the transition mechanics and supplies no
technical verdict (`.ai/workflow/ROLES.md`). In `review` the route is the
independent `reviewer`, not here — the review, repair, and completion gates
live in PROTOCOL.md §"Review and completion". Do not write `review.md` or judge
the change.
