# TICKET-006: CLI Test Suite

Type: task
Status: resolved
Blocked by: none

## Goal

Give the `ai-workflow` CLI its first automated regression protection. Round 1 (TICKET-001..005) was verified only manually ("V1 boundary, no test framework"); the kit's value proposition is machine-checkable enforcement, so its own machine must now be machine-checked. This ticket also fixes the one known parser data-loss bug (silent drop of deeper-indented content after an inline `- key: value` item, noted in TICKET-002), test-first.

## Decisions (recorded here, no new spec round needed)

The behavior under test is already specified: CLI commands in [spec §9](../../../docs/specs/agent-workflow-protocol.md), parser subset in [ADR-0002](../../../docs/adr/0002-restricted-yaml-subset-parser-over-pyyaml.md), state schema in `.ai/workflow/STATE_SCHEMA.md`. Only four decision-level points, not a spec:

1. **Framework: stdlib `unittest`** (not pytest). pytest is a third-party install; adding it would break the zero-dependency promise (ADR-0002) that lets any repo run `ai-workflow` immediately. Runner: `python -m unittest discover -s tests -v` from `scripts/ai-workflow/`.
2. **Tests live in `scripts/ai-workflow/tests/`** (test_parser.py, test_state.py, test_init.py, test_validate.py, test_adopt.py, test_main.py).
3. **Fix the silent-drop parser bug in this ticket** (first red test). Runtime remains Python 3 stdlib — see [ADR-0003](../../../docs/adr/0003-python-stdlib-cli-over-node.md).
4. **CI is out of scope** here; zero-dep means a CI step is trivial once a runner exists, but no CI config is added by this ticket.

## Plan (test matrix)

Write tests first, red where the bug lives, then fix.

- **test_parser.py** — template round-trip (must equal the shipped template text); rejection set (anchors `&`, aliases `*`, tags `!`, flow `{`/`[`, block scalars `|`/`>`, multi-doc `---`/`...`, root indented, map-in-sequence, dash-in-map); scalar coercion (null/bool/int/quoted/plain/comma-in-quotes); nested maps/lists/`[]`; comment stripping; **orphaned deeper-indented content raises instead of silently dropping** (the red tests).
- **test_state.py** — load missing/invalid file raises StateError; save stamps `updated_at`, leaves no `.tmp`, round-trips; unknown fields preserved across save/load.
- **test_init.py** — installs protocol + templates + `.agents/skills/` into a scratch repo; managed block appended exactly once; second run is a no-op (idempotent); user content outside the block preserved verbatim; unbalanced marker raises ManagedBlockError without touching the file; never overwrites pre-existing files.
- **test_validate.py** — clean state passes (no ERROR); gate-violating transition (insufficient → decisionward phase) ERROR; current_task > total ERROR; done-with-next_action ERROR; illegal phase/status/gate/role/scope ERROR; missing state.yaml ERROR; unparseable state.yaml ERROR; missing required artifacts per phase ERROR; missing handoff sections WARN only.
- **test_adopt.py** — adoption on a scratch repo produces migration report + state.yaml with `migration`/`historical_phases`/`adoption_checkpoint` blocks, `continuation_safe: false`, phase default requirement; `--phase` respected; second run idempotent no-op; adopted state validates clean at requirement; `decision.md` not fabricated.
- **test_main.py** — help exits 0, unknown command exits 2, command dispatch smoke.

## Fix (parser, after red)

In `parser.py`, after the `while` loop in `_build_map` and `_build_list`, a remaining entry that is **deeper-indented** than the current frame is orphaned content (the fixed schema/templates never produce it): raise `YAMLParseError` instead of returning and letting the entry be silently dropped. A shallower or same-indent entry must still fall through to the caller (legit sibling/sibling-of-parent).

## Constraints

- Tests use stdlib only (`unittest`, `tempfile`, `os`, `sys`); no pytest, no git dependency in tests (validate's git probe already tolerates non-repo dirs).
- Tests must be runnable with one command from `scripts/ai-workflow/` on Windows.
- The fix must not change behavior for anything the fixed schema/templates produce.

## Definition of done

- `python -m unittest discover -s tests -v` from `scripts/ai-workflow/` passes fully (run on Windows).
- The silent-drop case (`- a: 1` followed by a deeper-indented line) now raises a clear error instead of losing data; a regression test covers it.
- No change in behavior for valid schema/template state files (template round-trip test guards this).

## Comments

- 2026-09-21 — TICKET-006 created. Decisions (unittest / tests dir / bug rides along / no CI) agreed in conversation; recorded above. No new spec round — behavior is already specified (spec §9, ADR-0002, STATE_SCHEMA.md); ADR-0003 recorded the Python-vs-Node runtime decision this ticket's plan depends on.
- 2026-09-21 — TICKET-006 complete. Added `scripts/ai-workflow/tests/` with six stdlib-unittest files (`test_parser.py`, `test_state.py`, `test_init.py`, `test_validate.py`, `test_adopt.py`, `test_main.py`); runner `python -m unittest discover -s tests -v` from `scripts/ai-workflow/` (Windows-verified). First run: 56/59 green, 3 red — exactly the orphaned-content silent-drop cases. Fixed `parser.py` `_build_map`/`_build_list`: after the block loop, a remaining entry that is deeper-indented than the current frame now raises `YAMLParseError` ("unexpected indented content after map entry/sequence item") instead of being silently dropped. Final: 59/59 OK, and the shipped template still round-trips exactly (regression guard). No behavior change for anything the fixed schema/templates produce; legit same-indent siblings and shallower continuation still parse. ADR-0003 (`docs/adr/0003-python-stdlib-cli-over-node.md`) recorded: Python 3 stdlib stays for the core CLI; a future MCP-server adapter (official Python MCP SDK) is the only condition that would revisit the runtime, and it would be a separate component, never a rewrite.
