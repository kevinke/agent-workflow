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

1. Read `.ai/work/<ticket-id>/state.yaml` first — it is authoritative.
2. Confirm `next_action.role` is `scout`. If it is not, do not act; hand back.
3. Read the protocol files listed in PROTOCOL.md §"Entering a ticket" that apply
   (at minimum `.ai/workflow/PROTOCOL.md`, `.ai/workflow/ARTIFACTS.md`).
4. Read the source artifacts referenced by `source_artifacts` in state.yaml
   (spec, ticket, plan). Reference them by path; never copy their content.
5. Record your working session:
   `ai-workflow claim <ticket-id> --harness <H> --model <M>`.
6. Collect repository facts only into `evidence.md` per the Scout Report
   contract in `.ai/workflow/ARTIFACTS.md` (full worked examples:
   `.ai/workflow/examples/scout-bug.md`, `.ai/workflow/examples/scout-feature.md`):
   - Capture the snapshot first: current HEAD as `observed_commit`, relevant
     dirty paths as `dirty_changes`.
   - Draft Decision Questions from the request when the ticket supplies none;
     tie each to the decision it affects. Three to eight is guidance.
   - Record findings as FACT / INFERENCE / UNKNOWN with stable F-IDs, precise
     anchors, the verification method (static / execution / test), and scope.
     Negative searches state scope and exclusions.
   - If the request's ambiguity requires an architectural choice, escalate it;
     do not silently pick an architecture.
   - Temporary diagnostics (throwaway runs, probes) are permitted; record
     their outcome and any residual changes.
   - Stop when questions are answered or the remaining gaps and stopping
     reason are explicit. An exhausted budget yields a partial report with
     precise unknowns, not a verdict.
   Design proposals and your own sufficiency verdict are forbidden in
   evidence.md — a critical UNKNOWN can still leave the report ready for
   audit; only the auditor opens the Gate.
7. Do not touch `evidence.round` / `evidence.gate` / `phase` / `next_action`:
   the auditor records the round and verdict via `ai-workflow set-gate`, and
   the checkpoint-handoff advances the phase via `ai-workflow advance`. Leave
   those to them.
8. Write `handoff.md` per the contract before stopping (fixed sections +
   Repository State block).
9. Commit per the protocol's commit discipline, or report readiness for the
   next phase transition.

Do not record the evidence verdict; do not write `decision.md`; do not advance
the phase (`ai-workflow advance`). Those belong to other roles.
