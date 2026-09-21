# TICKET-004: Harness Adapters

Type: task
Status: open
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
