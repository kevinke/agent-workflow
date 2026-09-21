# TICKET-002: Workflow CLI

Type: task
Status: open
Blocked by: 01

## Goal

Make the state machine runnable: a zero-dependency Python 3 stdlib CLI with `init`, `status`, `validate` (and the restricted YAML parser behind them). This is the first machine-checkable enforcement of the protocol.

## Deliverables

Under `scripts/ai-workflow/`:

- `parser.py` — hand-written restricted YAML subset parser (nested maps, lists, scalars, null) per ADR-0002. Rejects syntax outside the subset with a clear error. No PyYAML.
- `state.py` — state.yaml load/save on top of the parser; unknown fields preserved or dropped (silently ignored, never error), `updated_at` stamped on save.
- `init.py` — install protocol + templates into a target repo. Idempotent: create `.ai/workflow/` and `.agents/skills/` if absent, never overwrite existing files, respect the managed-block rules (§12 of spec) when touching AGENTS.md. Must not modify any user content outside the managed block.
- `status.py` — one-screen summary: ticket, phase, status, task N/M, evidence gate, escalation, next role/action.
- `validate.py` — two severities: ERROR (illegal schema, gate-violating transition e.g. insufficient→technical_decision, current_task>total, missing artifact, DONE with next_action, handoff missing) and WARN (uncommitted work, missing handoff fields). Non-zero exit on ERROR.
- `__main__.py` or `main.py` wiring `ai-workflow <command>`.

## Constraints

- Zero third-party dependencies (Python 3 stdlib only).
- Works cross-platform (Windows included).
- Commands are non-destructive: `init` never deletes or overwrites user files; `validate` is read-only.
- State machine transitions must match the spec §4 exactly; do not invent transitions.

## Definition of done

- `ai-workflow init` on a scratch repo creates `.ai/workflow/` + templates; re-running it is a no-op (idempotent) and leaves user files untouched.
- `ai-workflow status` reads a template-derived state.yaml and prints the summary.
- `ai-workflow validate` flags a deliberately corrupted state.yaml (e.g. gate=insufficient but phase=technical_decision, or current_task>total) as ERROR with non-zero exit, and clean state as pass.
- Parser handles the full template + spec §5 example without dependency on PyYAML.
- Manual verification only (no test framework yet, per V1 boundary); note what was run in progress.md.

## Comments
