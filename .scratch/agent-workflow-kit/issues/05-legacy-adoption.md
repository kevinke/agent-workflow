# TICKET-005: Legacy Adoption

Type: task
Status: resolved
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

- 2026-09-21 — TICKET-005 complete. Authored `.ai/workflow/MIGRATION.md` (English) — the adoption procedure (discovery → migration report → phase reconstruction → retroactive minimum evidence → decision reconstruction → adoption checkpoint), matching spec §10 exactly and matching the section names the `workflow-bootstrap` skill routes to. Implemented `scripts/ai-workflow/adopt.py` (zero-dep, non-destructive, idempotent) + wired `adopt` into `main.py` (`ai-workflow adopt <ticket-id> [--phase --title --spec --ticket --plan]`). `adopt` runs mechanical discovery, writes `.ai/migration-report.md`, and scaffolds `.ai/work/<ticket>/`: state.yaml carrying the `migration` / `historical_phases` (scaffolded `not_performed`, senior fills with anchors) / `adoption_checkpoint` (all false, `continuation_safe: false`) blocks per spec §10, plus evidence/handoff/progress scaffolds. It does not fabricate history and does not start a decision.md (senior reconstructs it). A cheap executor is gated: `next_action.role` is `workflow-bootstrap` and `continuation_safe` is false until a senior confirms the checkpoint.
Manually verified on throwaway fixture repos (V1 boundary, no test framework): (1) case C (old repo with half-done ticket) — `adopt --phase implementation` produced the migration report and the state migration blocks; pre-existing AGENTS.md/README left byte-for-byte untouched; a second `adopt` was a no-op (idempotent). (2) Completed the senior adoption per MIGRATION.md on the fixture (retroactive `evidence.md` with Migration Notice, `evidence-audit.md`, `decision.md` reconstruction with Provenance, set `evidence.gate=sufficient` and all six checkpoint items true) → `validate` passed (exit 0, only benign WARNs). (3) case A (fresh repo, no `--phase`) → scaffolded at `requirement`, `continuation_safe: false`, validate clean immediately. Fixtures removed after verification; kit files unaffected beyond the three new/changed files.
- **Discovered parser quirk (TICKET-002 code, not fixed here):** the restricted parser's `_is_flowlike` guard rejects any inline scalar containing `,` as flow-style, even inside a double-quoted string, and `dump` will quote a string containing commas — so `dump`/`parse` are not round-trip-consistent for a quoted scalar with a comma. The fixed schema/template never produce one (template `next_action.action` has no comma). `adopt.py` deliberately writes its `next_action` prose without commas/parens to stay clear of it. Recommend a follow-up fix to `_is_flowlike` (drop `,`, keep only `{ } [ ]` delimiters) in a later ticket if round-tripping arbitrary comma-bearing strings is needed.
