# Protocol: Repo-native Cross-Harness Agent Workflow

Canonical sources: the spec `docs/specs/agent-workflow-protocol.md` and ADRs 0001/0002 in the kit repo. This directory is the protocol as installed into a target repository.

## 1. Goal

Any coding agent that can read and write a Git repository (Codex, TRAE, ZCode, ...) can, on entering the repo, determine from a small set of fixed files:

> what task -> which phase -> what evidence exists -> what the next role/action is

without relying on chat history. The repository is the only persistent source of truth for workflow state.

## 2. Core principles

1. The Git repository is the only persistent source of truth for workflow state.
2. `.ai/workflow/` holds the protocol and templates; `.ai/work/<ticket-id>/` holds ticket-level state and artifacts.
3. `state.yaml` is the machine-readable authoritative workflow state — the first file any harness reads.
4. Skills, AGENTS.md managed blocks, and project rules are adapters pointing at this protocol; they never copy protocol content.
5. Never overwrite existing repo documentation; existing specs, tickets, and plans are integrated by reference.
6. All install and migration operations are idempotent, non-destructive, and rollback-capable.

## 3. Entering a ticket

1. Read `.ai/work/<ticket-id>/state.yaml`. It is authoritative; chat history is never authoritative.
2. Note `phase` and `status`. The intended next step is `next_action`.
3. Check `claim`. If another session holds the claim, read `handoff.md` before doing anything.
4. Confirm your role matches `next_action.role` (see ROLES.md). If not, do not act; hand back.

## 4. Phases and statuses

The phase machine is linear with one evidence loop:

```
UNINITIALIZED -> REQUIREMENT -> EVIDENCE_COLLECTION -> EVIDENCE_AUDIT
  -> (evidence insufficient) -> FOLLOWUP_EVIDENCE -> EVIDENCE_AUDIT
  -> TECHNICAL_DECISION -> PLANNING -> IMPLEMENTATION -> REVIEW -> DONE
```

In `state.yaml`, phases are lowercase: `requirement`, `evidence_collection`, `evidence_audit`, `followup_evidence`, `technical_decision`, `planning`, `implementation`, `review`, `done`.

Lateral statuses are orthogonal to phase and are never merged into it: `active`, `blocked`, `escalation_required`, `paused`, `abandoned`.

A phase changes only via the transitions above. Do not invent transitions.

## 5. Claim semantics

`claim: {harness, model, claimed_at}` records which session is working on the ticket. It is a soft claim — advisory, not a lock. Set it when you begin a working session. A conflicting session must read `handoff.md` before taking over.

## 6. Reading and updating state.yaml

- Read `state.yaml` before acting; save it after every state change.
- Stamp `updated_at` on every save.
- Write only the restricted YAML subset documented in STATE_SCHEMA.md.
- Unknown fields are silently ignored — never an error, never deleted.
- Reference existing specs, tickets, and plans by path in `source_artifacts`; never copy them into `.ai/`.

## 7. Writing artifacts

Artifact contracts are in ARTIFACTS.md. In brief: evidence.md is collected by a scout; evidence-audit.md answers only sufficiency questions; decision.md is senior-only; progress.md logs at task granularity; handoff.md has fixed sections plus a Repository State block. Each artifact's writer is defined in ROLES.md.

## 8. Escalation

Escalations are recorded in `state.yaml` (`escalation` block) and handled per ESCALATION.md. Two scopes: `machine` (default — resolved by a senior role, never interrupts the user) and `human` (the only scope that interrupts the user).

## 9. Handoff discipline

Before stopping work on a ticket:

1. Update `state.yaml` to reflect the current phase, status, and progress.
2. Write `handoff.md` with the fixed sections and the Repository State block.
3. Run `ai-workflow validate`; no ERROR findings may remain. Any WARN findings are recorded in handoff.md.
4. Leave the working tree interpretable: the next agent must be able to continue from `state.yaml` + `handoff.md` alone.

## 10. Commits and rollback

- Commit at every phase boundary; during implementation, commit per task.
- Every work commit uses the prefix `ai-workflow(<ticket-id>): <action>`, e.g. `ai-workflow(TICKET-017): task 4 complete`. Grepping `ai-workflow(` recovers the whole work history.
- The phase-boundary commit is both the handoff anchor and the rollback point.
- Recovery from a botched phase: `git revert` to the last phase-boundary commit, then record an `incident` block in `state.yaml` explaining what went wrong and how it was recovered.
- `abandoned` tickets stay on disk and can be resurrected by a senior role: roll back to the last boundary commit, record an incident block, re-claim.

## 11. Legacy adoption

For repos adopted from existing state (existing specs, tickets, plans, half-done work), follow MIGRATION.md: discovery -> migration report -> phase reconstruction -> retroactive minimum evidence -> decision reconstruction -> adoption checkpoint. Never fabricate artifacts for phases that were never executed.
