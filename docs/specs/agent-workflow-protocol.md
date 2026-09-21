# Spec: Repo-native Cross-Harness Agent Workflow Protocol

Status: confirmed via grilling (2026-09-21). Source decisions: [ADR-0001](docs/adr/0001-repo-native-protocol-over-harness-skills.md), [ADR-0002](docs/adr/0002-restricted-yaml-subset-parser-over-pyyaml.md).

## 1. Goal

Any coding agent that can read and write a Git repo (Codex, TRAE, ZCode, …) can, on entering the repo, determine from a small set of fixed files:

> what task → which phase → what evidence exists → what the next role/action is

without relying on chat history. The repo itself is the source of truth for workflow state.

**Non-goals for V1:** no MCP, no database, no web UI, no Langfuse, no complex orchestrator. V1 is Markdown/YAML + Git.

## 2. Core principles

1. The Git repository is the only persistent source of truth for workflow state.
2. `.ai/workflow/` holds the protocol and templates.
3. `.ai/work/<ticket-id>/` holds ticket-level state, evidence, audit, decision, progress, handoff.
4. `state.yaml` is the machine-readable authoritative workflow state — the first file any harness reads.
5. Skills / AGENTS.md / TRAE rules are adapters, never the protocol itself.
6. Must support both greenfield repos and existing/legacy repo adoption.
7. Legacy migration must not fabricate historical workflow artifacts; distinguish confirmed / inferred / unknown.
8. Half-done tickets get Retroactive Minimum Evidence only — no full re-walk of history.
9. Never overwrite existing Matt, Superpowers, AGENTS.md, or repo docs; existing spec/ticket/plan are integrated by reference.
10. All install and migration operations are idempotent, non-destructive, rollback-capable.

## 3. Repository layout

```
repo/
├── AGENTS.md                  # managed block appended (create/update in place)
├── .ai/
│   ├── workflow/
│   │   ├── PROTOCOL.md
│   │   ├── STATE_SCHEMA.md
│   │   ├── ARTIFACTS.md
│   │   ├── ROLES.md
│   │   ├── ESCALATION.md
│   │   ├── MIGRATION.md
│   │   └── templates/
│   │       ├── state.yaml
│   │       ├── evidence.md
│   │       ├── evidence-audit.md
│   │       ├── decision.md
│   │       ├── progress.md
│   │       └── handoff.md
│   └── work/
│       └── <ticket-id>/
│           ├── state.yaml
│           ├── evidence.md
│           ├── evidence-audit.md
│           ├── decision.md
│           ├── progress.md
│           └── handoff.md
├── .agents/
│   └── skills/
│       ├── repo-scout/            # SKILL.md
│       ├── evidence-auditor/      # SKILL.md
│       ├── technical-decision/    # SKILL.md
│       ├── executor-plan/         # SKILL.md
│       ├── ticket-executor/       # SKILL.md
│       ├── checkpoint-handoff/    # SKILL.md
│       └── workflow-bootstrap/    # SKILL.md
└── docs/
```

`scripts/ai-workflow/` holds the CLI (init, status, validate, start, adopt, upgrade).

## 4. State machine

```
UNINITIALIZED
  → REQUIREMENT
  → EVIDENCE_COLLECTION
  → EVIDENCE_AUDIT
  → (evidence insufficient) → FOLLOWUP_EVIDENCE → EVIDENCE_AUDIT
  → TECHNICAL_DECISION
  → PLANNING
  → IMPLEMENTATION
  → REVIEW
  → DONE
```

Lateral statuses (never merged with phase): `active`, `blocked`, `escalation_required`, `paused`, `abandoned`.

```yaml
phase: implementation
status: blocked
```

## 5. `state.yaml` schema

`schema_version: 1`, `workflow_version: 1` from day one. Key blocks:

```yaml
schema_version: 1
workflow_version: 1
ticket: {id, title}
phase: <phase>
status: <lateral status>
repository: {base_commit, branch}
source_artifacts: {spec: {path}, ticket: {path}, plan: {path}}   # reference, never copy
artifacts: {evidence, evidence_audit, decision, progress, handoff}  # filenames
evidence: {round, gate: sufficient|insufficient}
implementation: {current_task, total_tasks, completed_tasks: []}
escalation: {required, scope: machine|human, reason}
claim: {harness, model, claimed_at}          # soft claim
next_action: {role, action, task}
provenance: {last_harness, last_model}
updated_at: <ISO-8601>
```

Rules:
- Unknown fields are **silently ignored**, never error.
- `state.yaml` uses only the restricted YAML subset (nested maps, lists, scalars, null) — enforced by validate (ADR-0002).

## 6. Artifact contracts (`.ai/work/<ticket-id>/`)

- **evidence.md** — only `FACT` / `INFERENCE` / `UNKNOWN`; important FACTs carry anchors (file path, symbol, line, command, test result). Design proposals are forbidden.
- **evidence-audit.md** — answers only: is evidence sufficient? what's missing? why might the gap change a decision? what should the next scout collect precisely?
- **decision.md** — written only by a senior model. Contains: chosen approach, rejected alternatives, invariants, compatibility, API/schema decisions, risks, escalation boundaries.
- **progress.md** — execution log at task granularity: completed task, files changed, tests run, deviation from plan, open issues. Not every shell command.
- **handoff.md** — fixed sections: What was done / What remains / Important discoveries / Current failure if any / Do not repeat / Next recommended action. Plus Repository State block: branch, HEAD, uncommitted files, test status.

## 7. Roles and model routing

| Role | Typical models | Phase scope |
|---|---|---|
| scout | cheap (DS Flash, GLM Flash) | evidence_collection, followup |
| evidence-auditor | senior (Terra/Sol) | evidence_audit |
| technical-decision | senior | technical_decision |
| executor-plan | senior | planning |
| ticket-executor | cheap | implementation (bounded) |
| checkpoint-handoff | any | phase transitions, handoff |
| workflow-bootstrap | senior | legacy adoption |

Model routing is encoded in the role definitions themselves; cheap agents collect evidence and execute bounded implementation, senior agents audit uncertainty, decide, plan, handle escalations, and review.

## 8. Escalation

Two scopes: `machine` (default, resolved by a senior role) and `human` (interrupts the user). During escalation, `next_action.role` locks to a senior role; senior clears `escalation.required` after resolution.

## 9. CLI (`scripts/ai-workflow/*.py`, Python 3 stdlib only, zero dependencies)

- `ai-workflow init` — install protocol + templates into target repo; idempotent (create / append managed block / update block); never touches user content outside the block.
- `ai-workflow status` — human/LLM-readable one-screen summary (ticket, phase, status, task N/M, evidence gate, escalation, next role/action).
- `ai-workflow validate` — two severities: ERROR (illegal schema, gate-violating transition, missing artifact) must be fixed before handoff; WARN may proceed but must be recorded. Validates the workflow itself, not code.
- `ai-workflow start <ticket-id>` — create `.ai/work/<ticket-id>/` from template; set phase per path (greenfield → REQUIREMENT; migration → adopted phase); write `source_artifacts` pointers.
- `ai-workflow adopt` — legacy repo migration (see §10).
- `ai-workflow upgrade` — explicit protocol upgrade using `workflow_version`.

## 10. Legacy adoption

Flow: **discovery** (scan AGENTS.md, README, docs, specs, tickets, plans, Matt/Superpowers artifacts, git status/branch/commits/diff, tests) → `migration-report.md` → **phase reconstruction** (confirmed/inferred/unknown per completed task, with evidence anchors) → **retroactive minimum evidence** (only what's needed to continue safely; file carries Migration Notice, is NOT a historical reconstruction) → **decision.md reconstruction** (with Provenance section; extracts only still-valid API/schema/invariants/architecture) → **adoption checkpoint** (`continuation_safe: true` before cheap agents can take over; otherwise a senior resolves uncertainty first).

`state.yaml` migration blocks:

```yaml
migration:
  adopted_existing_repo: true
  adopted_at_phase: implementation
historical_phases:
  requirement: {status: inferred}
  evidence_collection: {status: not_performed}
  ...
adoption_checkpoint:
  repository_understood: true
  active_ticket_identified: true
  current_phase_identified: true
  remaining_work_identified: true
  critical_invariants_identified: true
  continuation_safe: true
```

Never fabricate artifacts for phases never executed; never require re-walking history.

## 11. Git discipline

- Phase-boundary commits (implementation: per-task commits). Prefix `ai-workflow(<ticket-id>): <action>`.
- Before handoff: working tree must be interpretable; handoff records branch, HEAD, uncommitted files, test status.
- Rollback = `git revert` to last phase-boundary commit; record an `incident` block in state.yaml.
- `abandoned` tickets stay on disk and can be resurrected (senior role, rollback, incident block, re-claim).
- Multi-ticket parallelism allowed; one branch per ticket.

## 12. Harness adapters

- **Codex / ZCode**: managed block appended to `AGENTS.md` (`<!-- BEGIN/END AI-WORKFLOW -->`): read state.yaml, follow current phase/role, read only required artifacts, never redo completed phases, update state + handoff before stopping.
- **TRAE**: thin project rule pointing at PROTOCOL.md + state.yaml. Adapters never copy protocol content (avoids three drifting copies on protocol v2).

## 13. Delivery tickets (execution order)

1. **TICKET-001 — Core Protocol**: PROTOCOL.md, ROLES.md, ARTIFACTS.md, STATE_SCHEMA.md, ESCALATION.md, templates. No skills yet. Review design first.
2. **TICKET-002 — Workflow CLI**: init, status, validate (+ restricted YAML parser). Make the state machine run.
3. **TICKET-003 — Skills**: repo-scout, evidence-auditor, technical-decision, executor-plan, ticket-executor, checkpoint-handoff (+ workflow-bootstrap).
4. **TICKET-004 — Harness Adapters**: Codex/ZCode AGENTS.md managed block, TRAE project rule. Test: existing AGENTS.md not broken, reinstall idempotent.
5. **TICKET-005 — Legacy Adoption**: adopt command, migration report, phase reconstruction, retroactive minimum evidence, adoption checkpoint, validation. Senior model plans/implement/reviews this one.

Do not implement the whole system at once. Protocol design matters more than code volume.
