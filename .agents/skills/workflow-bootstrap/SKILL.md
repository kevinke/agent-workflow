---
name: workflow-bootstrap
description: Route legacy repo adoption to the protocol's MIGRATION.md. Senior-model role. Use when adopting an existing/legacy repo or a half-done ticket into the workflow.
---

# workflow-bootstrap

A thin pointer for legacy adoption. The full procedure is the protocol's
migration guide — this skill only routes to it.

## Procedure

1. Read `.ai/workflow/MIGRATION.md` — that document is the authority for legacy
   adoption: the whole procedure (discovery, migration report, phase
   reconstruction, retroactive minimum evidence, decision reconstruction,
   adoption checkpoint) and its non-negotiable rules live there.
2. If `.ai/workflow/MIGRATION.md` does not exist in the target repo, the
   migration capability has not been deployed there yet (it is delivered with
   the adoption ticket). Report that instead of improvising a migration.
3. The adoption State blocks (`migration`, `historical_phases`,
   `adoption_checkpoint`) have their field contracts in
   `.ai/workflow/STATE_SCHEMA.md` §"Migration blocks" and their procedure in
   MIGRATION.md §"Adoption checkpoint". No CLI command mutates them: a senior
   confirms the checkpoint per those documents and sets the fields as they
   prescribe.
4. Enter the normal flow with
   `ai-workflow advance <ticket-id> --to <phase>` after the checkpoint is
   complete, and verify with `ai-workflow validate`.

Follow MIGRATION.md exactly — its "Rules that never bend" section owns the
adoption rules, including when a ticket may be handed to a cheap executor.
