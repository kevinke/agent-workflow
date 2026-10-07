# TRAE project rule — agent-workflow adapter

This repo participates in the repo-native agent workflow protocol. This rule is a thin adapter: it points at the protocol, it does not copy it.

- Read `.ai/workflow/PROTOCOL.md` before starting any ticket work.
- Treat `.ai/work/<ticket>/state.yaml` as the authoritative workflow state — the first file any agent reads; it encodes the current phase, status, and next role/action.
- Continue without chat history with `ai-workflow resume <ticket-id>`: it prints a read-only brief (Ticket, State, next role/action/task, repository identity, artifact paths/digests, continuation checks). It never writes state and points at reports instead of pasting them.
- Follow the current phase and role. Read only the artifacts you need. Never redo completed phases.
- Model tiers are Harness-local defaults: Scout and executor are cheap; auditor, decision, planner, and Reviewer are senior. A senior capability may also handle hard scouting or hard implementation. Decision phases may share a session; Review keeps an independent context. Missing tools or a reproduction environment are escalated, not guessed around.
- Write back to `.ai/work/<ticket>/` (state.yaml, artifacts, handoff.md) before stopping.
