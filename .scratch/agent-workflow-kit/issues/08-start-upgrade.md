# TICKET-008: `start` and `upgrade` CLI commands

Type: task
Status: resolved
Blocked by: 002, 005

## Goal

Complete the CLI surface promised in spec §9. `init`/`status`/`validate` shipped in
TICKET-002 and `adopt` in TICKET-005, but `start` and `upgrade` were left stubbed
as "later tickets" in `main.py`. This ticket implements them so the CLI matches the
spec: six commands, zero dependencies, idempotent and non-destructive.

## Deliverables

Under `scripts/ai-workflow/`:

- `start.py` — greenfield counterpart to `adopt`. `start(root, ticket_id, ...)`
  creates `.ai/work/<ticket-id>/` from the **bundled templates** (the shipped
  `templates/state.yaml` is parsed by the kit's own parser and filled with the
  real ticket identity — single source of truth, spec §9 "create from template").
  Phase defaults to `requirement`; `--phase` lets a senior start at a later phase
  (illegal phases fall back to `requirement`, same rule as `adopt`). `--spec`,
  `--ticket`, `--plan` are recorded as `source_artifacts` pointers, never copies.
  Scaffolds `evidence.md`/`handoff.md`/`progress.md`; `decision.md` is senior-only
  and `evidence-audit.md` comes when evidence is audited (same policy as `adopt`).
  Idempotent: a second `start` on the same ticket is a no-op. `repository` is
  filled from git when available.
- `upgrade.py` — explicit protocol upgrade. Reads the kit's bundled
  `workflow_version` (its own `templates/state.yaml`) and the version installed
  in the target. When the installed protocol is older, `upgrade` **overwrites**
  the target's `.ai/workflow/` docs + templates with the bundled ones (the one
  place an explicit upgrade overwrites — `init` never does) and bumps
  `workflow_version` in every ticket state.yaml that is older, preserving all
  other fields (STATE_SCHEMA.md: "bumped only by an explicit upgrade"). No-op
  when already current; `UpgradeError` when nothing is installed.
- `main.py` — dispatch + usage for `start` and `upgrade`; the not-implemented
  stub is removed.

## Decisions (recorded here, no new spec round needed)

1. `start` parses the shipped `state.yaml` template rather than hardcoding the
   schema dict (unlike `adopt`'s `_build_state`). This is what spec §9 means by
   "create from template" and keeps `start`'s output coupled to the template —
   if the template evolves, `start` evolves with it. The template is already
   guaranteed parseable because `init` installs it and the dogfood test parses it.
2. `upgrade` treats the kit's own `templates/state.yaml` as the single source of
   truth for `workflow_version` (no separate version constant to drift).
3. `upgrade` only acts when `installed_version < kit_version`; equal versions are
   a no-op. Bumping rewrites only the `workflow_version` field of older tickets;
   unparseable tickets are skipped (validate will flag them separately).
4. Dogfood: the E2E test now drives the real `ai-workflow start` CLI instead of
   hand-scaffolding the ticket, so the install→start→validate path is the
   regression net for the new command.

## Definition of done

- `ai-workflow start <ticket-id>` in a fresh repo creates a validating
  `requirement`-phase ticket; re-running it is a no-op.
- `ai-workflow upgrade` on an older installed protocol overwrites `.ai/workflow/`
  and bumps older tickets; on a current protocol it is a no-op; on a repo with no
  protocol it exits non-zero with a clear message.
- Full suite green: 81 tests (was 67).

## Comments

- 2026-09-21 — TICKET-008 complete. Added `scripts/ai-workflow/start.py`
  (template-derived greenfield ticket scaffold: state.yaml from the bundled
  template parsed by the kit's own parser, phase default requirement with
  `--phase` fallback to requirement on illegal values, `source_artifacts`
  pointers, evidence/handoff/progress scaffolds, idempotent no-op on existing
  ticket) and `scripts/ai-workflow/upgrade.py` (explicit protocol upgrade:
  version read from the kit's own template as single source of truth, overwrites
  `.ai/workflow/` when installed is older, bumps older tickets' workflow_version
  preserving all other fields, `UpgradeError` when nothing installed, no-op when
  current). Wired both into `main.py` (dispatch + usage, stub removed; start
  accepts `--title/--phase/--spec/--ticket/--plan`). Tests: new `test_start.py`
  (6 tests: scaffold+artifacts, phase option, illegal-phase fallback,
  source_artifacts, idempotent, validates clean) and `test_upgrade.py` (6 tests:
  no-op when current, overwrites older protocol, bumps older tickets preserving
  fields, leaves current tickets alone, idempotent, raises when not installed);
  `test_main.py` stub test replaced with usage-error tests for start/upgrade;
  `test_dogfood.py` setUp now drives the real `ai-workflow start` CLI (install →
  start → walk the phase machine) plus a new no-op-upgrade CLI test. Full suite:
  81/81 green (was 67).
