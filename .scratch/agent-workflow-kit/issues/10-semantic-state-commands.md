# TICKET-010: Semantic state commands (advance / claim / complete-task / set-gate / escalate)

Type: task
Status: in_progress
Blocked by: 002, 008

## Goal

Kill the "hand-write restricted YAML to advance a ticket" gap surfaced by the
TICKET-008 dogfood. Today the CLI is read-only + scaffold-only: there is no way
to move a ticket through the state machine except editing `state.yaml` by hand,
which risks (a) writing outside the restricted YAML subset and (b) driving an
illegal transition that only a later `ai-workflow validate` would catch.

Add **semantic state commands** that encode the state machine and the restricted
subset, so a harness declares intent and this module checks + mutates + saves
through the kit's own parser — rejecting illegal transitions and gate violations
**at write time**.

## Commands (all under `scripts/ai-workflow/`)

- `advance <ticket-id> --to <phase>` — only legal transitions (STATE_SCHEMA.md);
  decisionward targets require `evidence.gate=sufficient`; `evidence_audit`
  branches by gate (sufficient→technical_decision, insufficient→followup_evidence);
  sets a phase-appropriate default `next_action` (cleared at `done`).
- `claim <ticket-id> [--harness H] [--model M]` — set `claim` + `provenance`.
- `complete-task <ticket-id> [--total N]` — increment `current_task`, append to
  `completed_tasks`; reject when all tasks complete.
- `set-gate <ticket-id> --gate sufficient|insufficient [--round N]` — record the
  auditor's evidence verdict.
- `escalate <ticket-id> --scope machine|human --reason "..."` or `--clear` —
  set/clear the escalation block.

New module `mutate.py` implements them; `main.py` wires dispatch + usage. The
role skills become thin: "run `ai-workflow advance --to <phase>`", no YAML
editing.

## Decisions (recorded here, no new spec round needed)

1. Transition table is a literal encoding of STATE_SCHEMA.md's allowed edges;
   gate enforcement reuses `validate.DECISIONWARDS` (renamed from the private
   `_DECISIONWARDS` so both modules share one source of truth).
2. `advance` sets a **default next_action** per target phase (role = that
   phase's worker). If a harness needs a custom next_action it still edits YAML —
   `advance` covers the common path, it does not forbid the direct edit.
3. Exit codes: 2 = usage error (missing/unknown args), 1 = mutation rejected
   (illegal transition / bad gate / counters), 0 = applied.
4. Dogfood: the E2E lifecycle test drives the real CLI (`advance`, `set-gate`,
   `complete-task`) instead of hand-mutating state.yaml — the happy path becomes
   a regression net proving the whole flow works without hand-written YAML.
   Negative tests still hand-corrupt state (they test the validator, not the
   mutator).

## Definition of done

- `advance` walks requirement→…→done via the CLI with `validate` green at each
  boundary; illegal transitions and gate violations are rejected with clear
  messages and non-zero exit.
- `claim`/`complete-task`/`set-gate`/`escalate` write the expected blocks and
  round-trip through the kit's parser.
- Full suite green (previous 84 + new mutate/dogfood coverage).

## Comments

- 2026-09-21 — TICKET-010 complete. Added `scripts/ai-workflow/mutate.py`
  (advance/claim/complete-task/set-gate/escalate) with the transition table
  encoded from STATE_SCHEMA.md, gate enforcement on decisionward targets, the
  gate-branched exit from evidence_audit, and phase-appropriate default
  next_action (cleared at done). `validate.DECISIONWARDS` renamed from
  `_DECISIONWARDS` so write-time and validate-time use one rule. Wired the five
  commands into `main.py` via a shared `_cmd_mutate` driver (usage error → 2,
  rejected → 1) + `_parse_options` helper; USAGE/docstring updated. Tests: new
  `test_mutate.py` (13 tests: full chain incl. gate loop, illegal/same/unknown
  transitions, gate enforcement, missing ticket, unknown-field preservation,
  claim, complete-task increments/rejects, set-gate, escalate+clear); the
  dogfood E2E lifecycle now drives the real CLI (`advance`, `set-gate`,
  `complete-task`) instead of hand-mutating state.yaml — the happy path needs
  zero hand-written YAML. **Dogfood payoff:** the rewritten E2E immediately
  caught a real bug — `_parse_options` compared `--to` against a `known` set
  written without dashes (`{"to"}`), so every `advance` failed; fixed by passing
  the dashed option names. Full suite 97/97 (was 84).

