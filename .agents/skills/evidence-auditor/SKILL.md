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

1. Read `.ai/work/<ticket-id>/state.yaml` first — it is authoritative. When
   entering without chat history, `ai-workflow resume <ticket-id>` prints the
   read-only continuation brief (PROTOCOL.md §"Portable continuation").
2. Confirm `next_action.role` is `evidence-auditor`. If not, hand back.
3. Read `.ai/workflow/ARTIFACTS.md` for the evidence-audit contract (its
   Metadata, the four sufficiency questions, and what is forbidden), then read
   the ticket and spec source artifacts (by reference).
4. Read the current `evidence.md` and judge only what the contract asks:
   sufficiency. Assess it within the contract's four questions — nothing else.
5. Record your working session:
   `ai-workflow claim <ticket-id> --harness <H> --model <M>`.
6. Record the verdict:
   `ai-workflow set-gate <ticket-id> --gate <sufficient|insufficient> --round <N>`.
   The recorded verdict is bound to the audited artifacts
   (`.ai/workflow/ARTIFACTS.md` §"Gate binding"); follow that contract for
   staleness and re-audit conditions.
7. Do not advance the phase yourself: `ai-workflow advance` branches out of
   `evidence_audit` on the gate you just set (PROTOCOL.md §"Phases and
   statuses"), and the checkpoint-handoff performs it.
8. Write `handoff.md` per the contract in `.ai/workflow/ARTIFACTS.md` before
   stopping.
9. Commit per PROTOCOL.md §"Commits and rollback".

Do not write `decision.md`; do not advance the phase — the transition belongs
to the checkpoint-handoff via `ai-workflow advance`.
