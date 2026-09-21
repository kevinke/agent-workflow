# TICKET-009: init appends managed block after a blank-line separator

Type: task
Status: resolved
Blocked by: none

## Goal

Fix a formatting blemish surfaced by dogfooding (TICKET-008 dogfood run in a
copied repo): when `ai-workflow init` appends the AI-WORKFLOW managed block to
an `AGENTS.md` that ends with a single newline, the block starts on the very
next line with no blank line separating it from the last line of user content.

## Change

In `scripts/ai-workflow/init.py`, `_apply_managed_block` append branch now picks
a separator so the block is always preceded by a blank line (except when the
file is empty or already ends with one):

- empty file → no separator
- ends with `\n\n` → no separator (already blank)
- ends with `\n` → add `\n` (one more makes the blank line)
- no trailing newline → add `\n\n`

The update-in-place branch is unchanged. Content outside the block is still
never touched (spec §2.9 / TICKET-004 promise).

## Definition of done

- New tests in `test_init.py` cover: single-trailing-newline (blank line added),
  no-trailing-newline (blank line added), already-blank-line (not doubled).
- Full suite green: 84 tests (was 81).

## Comments

- 2026-09-21 — TICKET-009 complete. Added three regression tests
  (test_managed_block_appended_with_blank_line_separator,
  test_managed_block_appended_cleanly_when_file_has_no_trailing_newline,
  test_managed_block_not_doubled_when_file_ends_with_blank_line) — the first two
  went red against the old append logic, then fixed `_apply_managed_block`'s
  append branch to guarantee a blank-line separator. Full suite 84/84 (was 81).
