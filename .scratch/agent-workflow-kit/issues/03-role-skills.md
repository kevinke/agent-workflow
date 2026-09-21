# TICKET-003: Role Skills

Type: task
Status: open
Blocked by: 01

## Goal

Implement the role skills. These are thin operational procedures — the business rules live in the protocol (TICKET-001), skills only point at it. Each skill is a `SKILL.md` under `.agents/skills/<role>/`.

## Deliverables

Under `.agents/skills/`:

- `repo-scout/SKILL.md` — collect evidence: read PROTOCOL.md, read state.yaml, confirm current phase permits scout work, read source artifacts, collect evidence into evidence.md, update state.yaml, write handoff.md.
- `evidence-auditor/SKILL.md` — audit sufficiency: read state, ticket/spec, evidence; write evidence-audit.md; update evidence.gate and next_action.
- `technical-decision/SKILL.md` — senior-only: read evidence + audit; write decision.md; advance phase to planning; update state.
- `executor-plan/SKILL.md` — senior: write the implementation plan from decision.md; advance to implementation.
- `ticket-executor/SKILL.md` — cheap-model bounded execution: read plan + decision + evidence; implement current task; update implementation.completed_tasks/current_task in state.yaml; commit with the `ai-workflow(<ticket-id>): <action>` prefix; write progress.md.
- `checkpoint-handoff/SKILL.md` — phase transitions and handoff: verify state consistency, write handoff.md with the fixed sections + Repository State block, ensure validate-clean before handoff.
- `workflow-bootstrap/SKILL.md` — thin pointer for legacy adoption (the full procedure is TICKET-005; this skill just routes to MIGRATION.md).

## Constraints

- Each SKILL.md must be an operational procedure only: read protocol, read state, do the phase's role, write artifacts, update state, handoff. No protocol content duplicated (adapters, not copies — ADR-0001).
- Role-to-model guidance matches ROLES.md (cheap vs senior) exactly.
- Skills must be loadable by the harness conventions in use (Codex repo skills under `.agents/skills`); TRAE compatibility is a later adapter ticket.

## Definition of done

- All seven SKILL.md files exist and are thin (no protocol body copied).
- Walking a reader through repo-scout's steps from a fresh state.yaml produces a valid evidence.md + updated state.yaml consistent with the protocol.
- Skills do not invent phases, roles, or fields beyond the spec.

## Comments
