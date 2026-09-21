# TICKET-004: Harness Adapters

Type: task
Status: resolved
Blocked by: 01, 02

## Goal

Make each harness able to enter the workflow. Adapters are thin pointers to the protocol — never copies (so protocol v2 doesn't mean maintaining three drifting copies).

## Deliverables

- **Codex / ZCode**: managed block appended to `AGENTS.md`:
  ```markdown
  <!-- BEGIN AI-WORKFLOW -->
  ...read state.yaml; follow current phase/role; read only required artifacts;
  never redo completed phases; update state + handoff before stopping...
  <!-- END AI-WORKFLOW -->
  ```
  Installer logic belongs in the CLI (`ai-workflow init`, TICKET-002); this ticket provides the block content + tests that it integrates.
- **TRAE**: thin project rule (`project_rules.md` fragment): read `.ai/workflow/PROTOCOL.md`, treat `.ai/work/<ticket>/state.yaml` as authoritative workflow state, write back to `.ai/work/`. Adapter does not copy protocol body.

## Constraints

- Must not overwrite user content in an existing AGENTS.md — only the managed block is touched (spec §12).
- Reinstall must be idempotent (no duplicated blocks).
- Adapters reference the protocol; they contain no protocol rules of their own.

## Definition of done

- Applying the block to an existing AGENTS.md preserves all surrounding user content; applying twice yields one block.
- Codex and ZCode can both enter a ticket from the block alone (verify by reading, not by running harnesses).
- TRAE project rule fragment exists and is under the `adapters/` directory (or documented location).

## Comments

- 2026-09-21 — TICKET-004 complete. Finalized the Codex/ZCode managed block in `scripts/ai-workflow/init.py` (installer logic from TICKET-002): wording is the final thin pointer per spec §12 — read `.ai/work/<ticket>/state.yaml` first (authoritative), follow phase/role in `PROTOCOL.md`/`ROLES.md`, read only needed artifacts, never redo completed phases, update state.yaml + handoff.md before stopping; no protocol body copied (ADR-0001). Created `adapters/trae/project_rules.md` — TRAE thin project-rule fragment: read `PROTOCOL.md`, treat `state.yaml` as authoritative, follow phase/role, write back to `.ai/work/<ticket>/`; does not copy protocol body. Manual integration verification on a scratch repo (V1 boundary, no test framework): (1) `init` on an existing AGENTS.md preserved all user content verbatim (sentinel intact) and appended exactly one block; (2) second `init` was a no-op ("nothing to do: protocol already installed"), still exactly one BEGIN/END block, user content untouched; (3) protocol docs + all six templates installed. Readability check: Codex/ZCode can enter a ticket from the block alone (it names the entry files, the phase/role to follow, and the pre-stop writebacks). Scratch repo removed after verification; kit AGENTS.md untouched (managed block is for target repos, applied by `init`).
