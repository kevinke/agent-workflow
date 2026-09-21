# TICKET-001: Core Protocol

Type: task
Status: resolved
Blocked by: none

## Goal

Author the protocol layer only: `.ai/workflow/` docs and templates. No skills, no CLI, no adapters. This ticket is the design foundation — everything else references these files.

## Deliverables

Create under the repo root:

- `.ai/workflow/PROTOCOL.md` — the workflow itself: goal, how to enter a ticket, phase/status rules, reading and updating `state.yaml`, claim semantics, handoff discipline, validate-before-handoff, commit prefix and phase-boundary commits, rollback via git revert + incident block, unknown-field-ignored rule.
- `.ai/workflow/ROLES.md` — the seven roles (scout, evidence-auditor, technical-decision, executor-plan, ticket-executor, checkpoint-handoff, workflow-bootstrap), each with phase scope and model-routing guidance (cheap vs senior). This is where model routing is encoded.
- `.ai/workflow/ARTIFACTS.md` — contracts for evidence.md (FACT/INFERENCE/UNKNOWN + anchors), evidence-audit.md (sufficiency questions only), decision.md (senior-only, listed sections), progress.md (task-granularity log), handoff.md (fixed sections + Repository State block).
- `.ai/workflow/STATE_SCHEMA.md` — the `schema_version: 1` state.yaml schema (§5 of the spec), the restricted YAML subset (nested maps, lists, scalars, null; ADR-0002), and the rule that unknown fields are silently ignored.
- `.ai/workflow/ESCALATION.md` — two scopes (machine default, human), senior-role lock during escalation, resolution protocol.
- `.ai/workflow/templates/state.yaml`, `evidence.md`, `evidence-audit.md`, `decision.md`, `progress.md`, `handoff.md` — copyable templates matching the contracts.

## Constraints

- Protocol docs are written in English (they are instructions executed by LLMs across harnesses).
- Content must match the spec exactly: [docs/specs/agent-workflow-protocol.md](../../../docs/specs/agent-workflow-protocol.md). Do not invent new phases, statuses, roles, or fields.
- Respect [ADR-0001](../../../docs/adr/0001-repo-native-protocol-over-harness-skills.md) and [ADR-0002](../../../docs/adr/0002-restricted-yaml-subset-parser-over-pyyaml.md).
- `state.yaml` template must validate against the STATE_SCHEMA rules (this is the contract the CLI ticket will test against).

## Definition of done

- All six files + six templates exist.
- A reader (human or senior LLM) can answer from PROTOCOL.md + STATE_SCHEMA.md alone: what phase/status mean, how to claim, what to write before handoff, what `state.yaml` may contain.
- Templates are consistent with the contracts (spot-checked, not automated — validate comes in TICKET-002).

## Comments

- 2026-09-21 — TICKET-001 complete. Authored `.ai/workflow/PROTOCOL.md`, `ROLES.md`, `ARTIFACTS.md`, `STATE_SCHEMA.md`, `ESCALATION.md` and `templates/{state.yaml,evidence.md,evidence-audit.md,decision.md,progress.md,handoff.md}` (English, per constraint). All content strictly matches spec §4/§5/§6/§7 — no new phases, statuses, roles, or state.yaml fields. Respects ADR-0001 (adapters never copy protocol) and ADR-0002 (restricted YAML subset). Spot-checked: state.yaml template fields = STATE_SCHEMA.md top-level blocks = spec §5; templates match ARTIFACTS.md contracts; template uses only the restricted subset (block maps, dash lists, `[]` empty list, scalars, null). Formal validation deferred to TICKET-002.
