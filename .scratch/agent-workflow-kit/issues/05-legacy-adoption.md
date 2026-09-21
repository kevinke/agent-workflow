# TICKET-005: Legacy Adoption

Type: task
Status: open
Blocked by: 01, 02

## Goal

Adopt existing/legacy repos into the workflow without fabricating history. This is the highest-risk ticket (it touches already-working repos), so the plan and the core implementation must be done by a senior model, and the review must be senior-led.

## Deliverables

- `MIGRATION.md` under `.ai/workflow/` — the adoption procedure: discovery → migration report → phase reconstruction (confirmed/inferred/unknown per completed task, with evidence anchors) → retroactive minimum evidence (with Migration Notice; NOT a historical reconstruction) → decision.md reconstruction (with Provenance section; only still-valid API/schema/invariants/architecture) → adoption checkpoint (`continuation_safe: true` before cheap agents take over; otherwise a senior resolves uncertainty first).
- `adopt` command in the CLI (TICKET-002's CLI): produces `.ai/migration-report.md`, then reconstructs state.yaml with the migration/historical_phases/adoption_checkpoint blocks (spec §10).
- Adoption must support three cases: (A) fresh repo, (B) old repo no active ticket, (C) old repo with a half-done ticket — C is the priority.

## Constraints

- Never fabricate artifacts for phases never executed; never require re-walking full history (retroactive minimum evidence only).
- Never overwrite existing Matt/Superpowers/AGENTS.md/repo docs; existing spec/ticket/plan integrated by reference (source_artifacts).
- Adopt is idempotent and rollback-capable (per spec principle 10).
- `continuation_safe: false` until a senior confirms the six adoption-checkpoint items.

## Definition of done

- Running `ai-workflow adopt` on a fixture repo (with a spec, tickets, a plan, and code partway through implementation) produces a migration report, a state.yaml with correct historical_phases and adoption_checkpoint, and a retroactive evidence.md carrying the Migration Notice.
- `ai-workflow validate` passes on the adopted state.
- No pre-existing file was modified outside the workflow's own files.
- A cheap executor cannot read an execution instruction until continuation_safe is true.

## Comments
