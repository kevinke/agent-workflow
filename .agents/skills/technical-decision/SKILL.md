---
name: technical-decision
description: Write decision.md and advance a ticket to planning during technical_decision. Senior-model role only. Use when a ticket's next_action.role is "technical-decision" and evidence.gate is sufficient.
---

# technical-decision

A thin operational procedure. All business rules live in the protocol under
`.ai/workflow/`; read those files before acting. Do not restate protocol rules here.

## Phase scope

`technical_decision` (see `.ai/workflow/ROLES.md`). Senior-model role only.

## Procedure

1. Read `.ai/work/<ticket-id>/state.yaml` first — it is authoritative.
2. Confirm `next_action.role` is `technical-decision` and `evidence.gate` is
   `sufficient`. If either fails, do not act; escalate per `.ai/workflow/ESCALATION.md`.
3. Read `evidence.md` and `evidence-audit.md`.
4. Write `decision.md` per the contract in `.ai/workflow/ARTIFACTS.md`: chosen
   approach, rejected alternatives, invariants, compatibility, API/schema
   decisions, risks, escalation boundaries. Leave nothing undecided that the
   plan needs.
5. Update `state.yaml`: advance `phase` to `planning`, set `next_action` to the
   `executor-plan` role, set `claim` before work, update `provenance`.
6. Write `handoff.md` before stopping (fixed sections + Repository State block).
7. Commit per the protocol's commit discipline (phase-boundary commit).

If the decision depends on missing information, escalate rather than guess.
