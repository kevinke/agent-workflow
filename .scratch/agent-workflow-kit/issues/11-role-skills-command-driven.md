# TICKET-011: Role skills are command-driven (no hand-editing state.yaml)

Type: task
Status: resolved
Blocked by: 010

## Goal

TICKET-010 added the semantic state commands, but the seven role skills still
taught agents to hand-edit `state.yaml` ("Update `state.yaml`: set
`evidence.gate`…", "advance `phase` to…", "clear `next_action` in state.yaml").
Rewrite them so every state mutation goes through the CLI — a harness declares
intent and the commands enforce legality, never hand-written YAML.

## Change

Each `.agents/skills/<role>/SKILL.md` was rewritten to call the CLI for every
state mutation:

- **repo-scout** — `ai-workflow claim` before work; collects `evidence.md`;
  explicitly leaves `round`/`gate`/`phase`/`next_action` to other roles.
- **evidence-auditor** — records the verdict with `ai-workflow set-gate --gate
  ... --round N`; does not advance (the branch is `advance`'s job).
- **technical-decision** — `ai-workflow advance --to planning` (enforces gate).
- **executor-plan** — `ai-workflow advance --to implementation`; the executor
  sets task counters via `complete-task --total N`, not the planner.
- **ticket-executor** — `ai-workflow claim` + `ai-workflow complete-task
  [--total N]` per task; never advances the phase.
- **checkpoint-handoff** — `ai-workflow validate` first, then `ai-workflow
  advance --to <destination>` (clears `next_action` at done), `ai-workflow
  escalate --clear` for resolved escalations.
- **workflow-bootstrap** — routes to MIGRATION.md; notes that the
  adoption-specific blocks (`migration`/`historical_phases`/`adoption_checkpoint`)
  still have no CLI command (open gap, tracked in the improvement-2/4
  discussion), then enters the normal flow with `ai-workflow advance`.

## Tests

New `tests/test_skills.py` lints the skills: (a) no SKILL.md may contain the old
hand-edit phrasings ("Update `state.yaml`", "set `evidence.gate`", "advance
`phase` to", "clear `next_action` in state.yaml", "increment `evidence.round`"),
and (b) every skill references `ai-workflow`. The lint went red on all 7 skills
before the rewrite.

## Definition of done

- All 7 SKILL.md files reference the CLI for state mutations.
- Skills lint passes; full suite green: 99 tests (was 97).

## Comments

- 2026-09-21 — TICKET-011 complete. Rewrote all seven role skills to be
  command-driven; added `tests/test_skills.py` (2 lint tests). First green run
  caught my own repo-scout closing line using the banned phrase "set
  `evidence.gate`" (even as a negation) — rephrased. Full suite 99/99 (was 97).
