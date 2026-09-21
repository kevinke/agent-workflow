# TRAE project rule — agent-workflow adapter

This repo participates in the repo-native agent workflow protocol. This rule is a thin adapter: it points at the protocol, it does not copy it.

- Read `.ai/workflow/PROTOCOL.md` before starting any ticket work.
- Treat `.ai/work/<ticket>/state.yaml` as the authoritative workflow state — the first file any agent reads; it encodes the current phase, status, and next role/action.
- Follow the current phase and role. Read only the artifacts you need. Never redo completed phases.
- Write back to `.ai/work/<ticket>/` (state.yaml, artifacts, handoff.md) before stopping.
