---
name: repo-scout
description: Collect repository evidence into evidence.md during evidence_collection and followup_evidence. Use when a ticket's next_action.role is "scout" or when evidence is needed to continue a ticket. Cheap-model role; the business rules live in the protocol, not here.
---

# repo-scout

A thin operational procedure. All business rules live in the protocol under
`.ai/workflow/`; read those files before acting. Do not restate protocol rules here.

## Phase scope

`evidence_collection`, `followup_evidence` (see `.ai/workflow/ROLES.md`).

## Procedure

1. Read `.ai/work/<ticket-id>/state.yaml` first — it is authoritative. When
   entering without chat history, `ai-workflow resume <ticket-id>` prints the
   read-only continuation brief (PROTOCOL.md §"Portable continuation").
2. Confirm `next_action.role` is `scout`. If it is not, do not act; hand back.
3. Read the protocol files listed in PROTOCOL.md §"Entering a ticket" that
   apply — at minimum `.ai/workflow/PROTOCOL.md` (especially §"Scouting and
   auditing"), `.ai/workflow/ROLES.md`, and `.ai/workflow/ARTIFACTS.md`.
4. Read the source artifacts referenced by `source_artifacts` in state.yaml
   (spec, ticket, plan). Reference them by path; never copy their content.
5. Record your working session:
   `ai-workflow claim <ticket-id> --harness <H> --model <M>`.
6. Collect repository facts into `evidence.md` per the Scout Report contract in
   `.ai/workflow/ARTIFACTS.md` (worked examples:
   `.ai/workflow/examples/scout-bug.md`, `.ai/workflow/examples/scout-feature.md`).
   That contract owns the collection doctrine — sections, Decision Questions,
   the FACT / INFERENCE / UNKNOWN finding syntax, the stopping reason, and what
   is forbidden in evidence.md. Follow it exactly; this skill does not restate it.
7. The scout writes evidence and handoff only (PROTOCOL.md §"Scouting and
   auditing"): the evidence verdict is the auditor's (`ai-workflow set-gate`)
   and phase transitions belong to the checkpoint-handoff (`ai-workflow
   advance`). Leave both to them.
8. Write `handoff.md` per the contract in `.ai/workflow/ARTIFACTS.md` before
   stopping.
9. Commit per PROTOCOL.md §"Commits and rollback", or report readiness for the
   next phase transition.

Do not record the evidence verdict; do not write `decision.md`; do not advance
the phase (`ai-workflow advance`). Those belong to other roles (see
`.ai/workflow/ROLES.md`).
