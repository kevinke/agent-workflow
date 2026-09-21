---
name: workflow-bootstrap
description: Route legacy repo adoption to the protocol's MIGRATION.md. Senior-model role. Use when adopting an existing/legacy repo or a half-done ticket into the workflow.
---

# workflow-bootstrap

A thin pointer for legacy adoption. The full procedure is the protocol's
migration guide — this skill only routes to it.

## Procedure

1. Read `.ai/workflow/MIGRATION.md` — that document is the authority for legacy
   adoption (discovery, migration report, phase reconstruction, retroactive
   minimum evidence, decision reconstruction, adoption checkpoint).
2. If `.ai/workflow/MIGRATION.md` does not exist in the target repo, the
   migration capability has not been deployed there yet (it is delivered with
   the adoption ticket). Report that instead of improvising a migration.

Follow MIGRATION.md exactly: never fabricate artifacts for phases that were
never executed; never require re-walking full history; integrate existing
spec/ticket/plan by reference. A ticket must not be handed to a cheap executor
until the adoption checkpoint is `continuation_safe: true`.
