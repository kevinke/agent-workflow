# CONTEXT.md

Glossary for the agent-workflow kit. Terms are canonical: skills and protocol docs must use these words, not synonyms.

## Core concepts

- **Harness** — An AI coding agent runtime: Codex, TRAE, ZCode, etc. Harnesses differ in skill discovery and config formats, but all can read and write plain Git files.
- **Workflow Protocol** — The repo-native collaboration protocol defined in `.ai/workflow/`. It is the source of truth for how agents work on a ticket; Harness-specific config (skills, rules) is only an adapter to it.
- **Adapter** — A thin, Harness-specific entry point (managed block in `AGENTS.md`, TRAE project rule) that points the Harness at the Protocol. Adapters never copy Protocol content.
- **Ticket** — A unit of work. In repos using the matt-pocock flow, tickets live under `.scratch/<feature>/issues/`; the Protocol tracks execution state per ticket under `.ai/work/<ticket-id>/`.
- **Phase** — Where a ticket is in the workflow state machine (requirement → evidence_collection → evidence_audit → technical_decision → planning → implementation → review → done). Distinct from status.
- **Status** — The横向 condition of the current phase: active, blocked, paused, escalation_required, abandoned. Never merged into phase.
- **State (`state.yaml`)** — The machine-readable, authoritative per-ticket workflow state. The first file any Harness reads; chat history is never authoritative.
- **Artifact** — A markdown file with a strict contract under `.ai/work/<ticket-id>/`: evidence, evidence-audit, decision, progress, handoff. Each has a defined writer role and allowed content.
- **Evidence** — Repository facts recorded in `evidence.md`, each tagged FACT, INFERENCE, or UNKNOWN, with source anchors (file, symbol, line, command, test result).
- **Evidence Gate** — The auditor's verdict on whether evidence is sufficient to enter technical_decision. The state machine enforces it.
- **Claim (soft claim)** — A convention recorded in `state.yaml` (`claim: {harness, model, claimed_at}`) marking which session is working on a ticket. Advisory, not a lock; a conflicting session must read `handoff.md` before taking over.

## Migration concepts

- **Retroactive Minimum Evidence** — When adopting a half-done ticket, evidence is collected only for what is needed to safely continue remaining work, never a full historical reconstruction. The evidence file must carry a Migration Notice stating this.
- **Adoption Checkpoint** — The block in `state.yaml` set after migration (`continuation_safe`, etc.). A ticket may not be handed to a cheap executor until `continuation_safe: true`.
- **Historical phase status** — During migration, each past phase is marked confirmed, inferred, existing, or not_performed. Migration never fabricates artifacts for phases that were never executed.
- **Source Artifacts (reference, not copy)** — Existing specs, tickets, and plans (matt-pocock or otherwise) are referenced by path from `state.yaml`, never duplicated into `.ai/`.

## Operational concepts

- **Validate Severity** — `ai-workflow validate` findings are ERROR (illegal schema, gate-violating transition, missing artifact: must be fixed before handoff) or WARN (proceed allowed, but must be recorded in handoff).
- **Phase-boundary Commit** — At each phase end, artifacts, `state.yaml`, and code are committed together. The commit is both the handoff anchor and the rollback point; recovery from a botched phase is `git revert` to the last boundary.
- **Incident Block** — A `state.yaml` section recording that a phase went wrong, why, and how it was recovered, so the next agent knows a failure happened there.
- **Escalation Scope** — Every escalation is `machine` (resolved by a senior role: evidence shortage, decision conflict, plan deviation) or `human` (escalates to the user). Default is machine; only `human` interrupts the user.
- **Commit Prefix** — Work commits use the fixed prefix `ai-workflow(<ticket-id>): <action>`, e.g. `ai-workflow(TICKET-017): task 4 complete`. Grepping `ai-workflow(` recovers the whole work history. Commit granularity: per-task inside implementation, per-phase elsewhere.
- **Resurrect** — Reviving an `abandoned` ticket: roll back to the last phase-boundary commit, record an incident block, re-claim. Only a senior role decides which prior work stays valid.

## Repository concepts

- **Managed Block** — A marked section (`<!-- BEGIN/END AI-WORKFLOW -->`) appended to a repo's `AGENTS.md` by the installer. Installing is idempotent: create if absent, append if missing, update in place if present. User content outside the block is never touched.
- **Kit** — This repository: the source of the Protocol, skills, CLI, and adapters, installed into target repos by `ai-workflow init`.
