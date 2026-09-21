# TICKET-012: Kit polish — skills install story + set-status / release / updated_at

Type: task
Status: resolved
Blocked by: 011

## Goal

Four small improvements agreed after TICKET-011:

1. **Skills install story (improvement 2, option C — hybrid)**: by default the
   role skills live in the harness's global skill library (single source, zero
   drift); the optional "self-contained repo" path is now `ai-workflow init
   --with-skills` or `ai-workflow install-skills [target]`.
2. **set-status (4a)**: lateral statuses (`blocked`/`paused`/`abandoned`/…)
   had no command; `escalate` only covered `escalation_required`.
3. **release (4b)**: `claim` had no counterpart to clear the soft claim.
4. **validate updated_at (4c)**: `updated_at` is stamped on every save, so a
   missing value means hand-edited state — now a WARN.

## Change

- `scripts/ai-workflow/skills.py` (new) — `install_skills(target)`: copies the
  seven kit-owned `SKILL.md` files into the target's `.agents/skills/`, updating
  **in place** (unchanged files skipped → idempotent, changed files
  overwritten); never touches anything outside the seven kit-owned names.
- `main.py` — `init [target] [--with-skills]`, new `install-skills [target]`,
  `set-status <ticket> --status <s>`, `release <ticket>`; USAGE/docstring
  updated.
- `mutate.py` — `set_status` (validates against `validate.STATUSES`) and
  `release` (clears `claim`, keeps `provenance` for the audit trail).
- `validate.py` — WARN when `updated_at` is missing.

## Decisions (recorded here, no new spec round needed)

1. Skills install overwrites the seven kit-owned files in place (like the
   managed block): the kit's copy is authoritative for exactly those files;
   anything else in `.agents/skills/` is never touched.
2. `release` keeps `provenance`: it records *who worked last*, which the claim
   handoff must preserve; only the soft claim is cleared.
3. Missing `updated_at` is a WARN, not an ERROR: proceed allowed, record in
   handoff (matches the Validate Severity rule).

## Tests

- `test_skills.py` — install copies all 7 idempotently; second run writes
  nothing; a stale copy is updated in place.
- `test_mutate.py` — `set_status` (valid + illegal), `release` (claim cleared,
  provenance kept).
- `test_validate.py` — missing `updated_at` is WARN-only.
- `test_dogfood.py` — setUp now runs `init --with-skills` through the real CLI
  and asserts a skill file landed in the target repo.

## Definition of done

- `init --with-skills` / `install-skills` install the 7 skills (idempotent).
- `set-status`/`release` work through the CLI; `validate` warns on missing
  `updated_at`.
- Full suite green: 104 tests (was 99).

## Comments

- 2026-09-21 — TICKET-012 complete. Added `skills.py` (install_skills: 7
  kit-owned SKILL.md copied in place, idempotent, never touches other files),
  wired `init --with-skills` + `install-skills` + `set-status` + `release` into
  `main.py`, added `mutate.set_status`/`mutate.release`, and a missing-`updated_at`
  WARN in `validate.py`. Tests: +2 skills install, +2 mutate, +1 validate; dogfood
  setUp drives `init --with-skills` through the real CLI and asserts the skill
  files land. Real-CLI smoke: init --with-skills lists all 7 skills,
  install-skills is a no-op, set-status/release/validate all behave. Full suite
  104/104 (was 99).
