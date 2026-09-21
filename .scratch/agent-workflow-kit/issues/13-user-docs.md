# TICKET-013: User documentation (README + quickstart + adopting-existing)

Type: task
Status: resolved
Blocked by: 012

## Goal

The kit had protocol docs and ADRs but no user-facing "how do I use this" entry
point. Add a root README plus two linked guides covering: what the kit is, the
three-layer model (Matt content / kit state / Superpowers quality), a full
worked ticket walk, and the adopt-migration path for existing repos.

## Deliverables

- `README.md` (root) — positioning, core ideas, three-layer table, quickstart
  command sequence, adopt one-liner, full 14-command reference, doc map.
- `docs/users/quickstart.md` — greenfield ticket walked requirement→done with
  the exact CLI sequence, per-phase artifact requirements, git commit
  discipline, evidence-loop branch, and a troubleshooting table.
- `docs/users/adopting-existing.md` — adopt vs start, senior migration steps,
  source_artifacts-by-reference, skills install story (global vs --with-skills),
  and the per-phase Matt/Superpowers skill pairing.

## Definition of done

- README links to both guides; commands cited match the real CLI (verified
  against the dogfood lifecycle in `tests/test_dogfood.py`).

## Comments

- 2026-09-21 — TICKET-013 complete. Added README.md, docs/users/quickstart.md,
  docs/users/adopting-existing.md. All CLI examples cross-checked against the
  104-test suite's dogfood lifecycle.
