---
name: reviewer
description: Independently review the current change against the registered Plan and decision.md from inside a prepared isolated review snapshot, author a candidate review.md and handoff.md under its scratch area, and have the verdict published through the guarded ai-workflow set-review. Senior default in an independent context. Use when a ticket's next_action.role is "reviewer" or when a Review verdict must be recorded.
---

# reviewer

A thin operational procedure. All business rules live in the protocol under
`.ai/workflow/`; read those files before acting. Do not restate protocol rules here.

## Phase scope

`review` (see `.ai/workflow/ROLES.md`). Senior default; review in an independent
context, not the context that wrote the change.

Ownership: PROTOCOL.md §"Reviewer verification isolation and publication" owns
isolation, the candidate-only output rule and the publication procedure;
`.ai/workflow/ARTIFACTS.md` §"Verification provenance for new isolated reviews"
owns the reserved provenance section. Read both before acting.

## Procedure

1. Read `.ai/work/<ticket-id>/state.yaml` first — it is authoritative. When
   entering without chat history, `ai-workflow resume <ticket-id>` prints the
   read-only continuation brief (PROTOCOL.md §"Portable continuation").
2. Confirm `next_action.role` is `reviewer`. If not, hand back.
3. Read `.ai/workflow/ARTIFACTS.md` for the review contract and
   `.ai/workflow/PROTOCOL.md` (§"Review and completion") for the review, repair,
   and completion rules.
4. Read the registered Plan (referenced by `source_artifacts.plan`, never a
   copy) and `decision.md` (by reference). These are the contract under review.
5. Record your working session:
   `ai-workflow claim <ticket-id> --harness <H> --model <M>`.
6. Have the trusted coordinator — `checkpoint-handoff`, the role that also
   performs the guarded publication in step 9 — prepare your snapshot; running
   `prepare-review` is not yours to do. Then work only inside that
   prepared context `<dir>` created by
   `ai-workflow prepare-review <ticket-id> --commit <literal-oid> --output <dir>`:
   `<dir>/repo` is the disposable snapshot of the reviewed commit (the boundary's
   `/snapshot`), `<dir>/scratch` is your candidate output area, and `<dir>/meta`
   holds the supervisor's manifest and receipts. Independent context is not
   established by reading elsewhere: verification happens in the snapshot, which
   is where probes, modified tests, fixtures and caches may be written.
7. Independently verify the acceptance criteria against the actual change and
   the recorded verification results — do not trust the change's own summary.
   Read the code, tests, and evidence the task claims inside the snapshot, and
   run every verifier command through the enforced boundary:

   ```
   ai-workflow run-review <ticket-id> --review-context <dir> --kind baseline -- <argv...>
   ai-workflow run-review <ticket-id> --review-context <dir> --kind probe -- <argv...>
   ```

   `--kind baseline` is the acceptance run whose receipt your report quotes; a
   `--kind probe` run is a declared snapshot-relative edit that is restored or
   recorded as a residual change and never becomes a baseline. Each command exits
   with the verifier's own status; the receipt keeps failures, stdout/stderr
   hashes and residual snapshot changes. On a boundary blocker there is no
   isolated verification to perform: report the blocker and escalate per
   `.ai/workflow/ESCALATION.md` instead of running unconstrained.
8. Author the **candidate** Review and the **candidate** Handoff under
   `<dir>/scratch` (for example `scratch/review.md`, `scratch/handoff.md`) per the
   contracts in `.ai/workflow/ARTIFACTS.md` — that contract owns the required
   Metadata, the required sections, the reserved provenance section and what is
   forbidden. Fill the provenance section from the supervisor's own `<dir>/meta`
   records. You do not write the live `.ai/work/<ticket-id>/` records.
9. Hand the candidate to the trusted publisher. The guarded publication is
   performed by the publisher, not by you:
   `ai-workflow set-review <ticket-id> --verdict <pass|changes_requested> --review-context <dir> --report <scratch/review.md> --handoff <scratch/handoff.md>`.
   The recorded verdict is bound to the Review artifact, the reviewed commit and
   the registered Plan (`.ai/workflow/ARTIFACTS.md` §review.md;
   `.ai/workflow/STATE_SCHEMA.md` §"v2 Review binding"); follow those contracts
   for staleness and re-review conditions. Publication re-reads the live baseline
   first: a refusal means the review is no longer current and needs a fresh
   snapshot and a new independent review, and a prepared context publishes at most
   one verdict.
10. On `changes_requested`, the rework path is append-only (PROTOCOL.md
    §"Review and completion"): the senior registers an appending Plan and the
    ticket returns to `implementation`. Local repairs stay within the recorded
    decision; design or architecture changes escalate per
    `.ai/workflow/ESCALATION.md` — they are not improvised here.
11. Do not advance the phase yourself; the checkpoint-handoff performs the
    transitions (`review -> done`, the repair path), which the protocol gates
    on the recorded verdict.

You perform no live commit and no phase transition: publication writes only this
Ticket's Review, State and Handoff through the public command above. Do not write
production code or `decision.md`.
