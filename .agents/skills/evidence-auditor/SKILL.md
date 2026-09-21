---
name: evidence-auditor
description: Audit evidence sufficiency, write evidence-audit.md, and record the verdict with ai-workflow set-gate during evidence_audit. Use when a ticket's next_action.role is "evidence-auditor" or when evidence.gate must be set to sufficient or insufficient. Senior-model role.
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
6. Record your working session:
   `ai-workflow claim <ticket-id> --harness <H> --model <M>`.
7. Record the verdict:
   `ai-workflow set-gate <ticket-id> --gate <sufficient|insufficient> --round <N>`.
   `<N>` is the number of evidence-collection rounds you audited.
8. Do not advance the phase yourself: `ai-workflow advance` branches out of
   `evidence_audit` on the gate you just set (sufficient → `technical_decision`,
   insufficient → `followup_evidence`), and the checkpoint-handoff performs it.
9. Write `handoff.md` before stopping (fixed sections + Repository State block).
10. Commit per the protocol's commit discipline.

Do not write `decision.md`; do not advance the phase — the transition belongs
to the checkpoint-handoff via `ai-workflow advance`.
