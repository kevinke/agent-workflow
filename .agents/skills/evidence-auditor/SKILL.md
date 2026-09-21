---
name: evidence-auditor
description: Audit evidence sufficiency and write evidence-audit.md during evidence_audit. Use when a ticket's next_action.role is "evidence-auditor" or when evidence.gate must be set to sufficient or insufficient. Senior-model role.
---

# evidence-auditor

A thin operational procedure. All business rules live in the protocol under
`.ai/workflow/`; read those files before acting. Do not restate protocol rules here.

## Phase scope

`evidence_audit` (see `.ai/workflow/ROLES.md`).

## Procedure

1. Read `.ai/work/<ticket-id>/state.yaml` first — it is authoritative.
2. Confirm `next_action.role` is `evidence-auditor`. If not, hand back.
3. Read `.ai/workflow/ARTIFACTS.md` for the evidence-audit contract, then read
   the ticket and spec source artifacts (by reference).
4. Read the current `evidence.md`.
5. Write `evidence-audit.md` answering only the four sufficiency questions in
   the contract. No recommendations, no designs.
6. Update `state.yaml`: set `evidence.gate` to `sufficient` or `insufficient`.
   If `insufficient`, the next phase is `followup_evidence` and `next_action.role`
   returns to `scout`; if `sufficient`, the next phase is `technical_decision`
   and the next role is `technical-decision`. Set `claim` before work, update
   `provenance` on save.
7. Write `handoff.md` before stopping (fixed sections + Repository State block).
8. Commit per the protocol's commit discipline.

Do not write `decision.md`; do not advance the phase to `technical_decision` —
the transition is recorded in state.yaml only.
