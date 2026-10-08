# TRAE project rule — agent-workflow adapter

This repo participates in the repo-native agent workflow protocol. This rule is a thin adapter: it points at the protocol, it does not copy it.

- Read `.ai/workflow/PROTOCOL.md` before starting any ticket work.
- Treat `.ai/work/<ticket>/state.yaml` as the authoritative workflow state — the first file any agent reads; it encodes the current phase, status, and next role/action.
- Continue without chat history with `ai-workflow resume <ticket-id>`: it prints a read-only brief (Ticket, State, next role/action/task, repository identity, artifact paths/digests, continuation checks). It never writes state and points at reports instead of pasting them.
- Follow the current phase and role. Read only the artifacts you need. Never redo completed phases.
- Model tiers, session sharing, and the escalate-don't-guess rule are Harness-local defaults defined in `.ai/workflow/ROLES.md` (§"Model routing and continuation"); read it instead of assuming a mapping here.
- Write back to `.ai/work/<ticket>/` (state.yaml, artifacts, handoff.md) before stopping.
