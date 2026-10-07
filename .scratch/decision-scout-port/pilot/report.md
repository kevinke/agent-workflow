# Pilot Report — Measured Live Model/Harness Handoff (SCOUT-008)

Status: **PENDING — no real model session run.**
Date prepared: 2026-10-07 (Task 1). Runs performed: **none**.

Procedure: [runbook.md](runbook.md). Plan Task 2, spec Testing Decisions, issue
[08-live-model-harness-pilot.md](../issues/08-live-model-harness-pilot.md).

## Explicit blocker (why this is pending, not passed)

The pilot requires **actual** inexpensive Scout, senior, executor and independent
review sessions plus at least one persisted handoff between two real Harnesses
(spec Testing Decisions; issue AC 1–2, 7). Per the binding external-budget ruling
(runbook §0), Task 1 may only *probe* availability and must not launch a real
model session that spends the user's external quota/credentials. No such consent
was given for Task 1, so **no real session was launched** and no run record
exists.

Concrete unverified access at the time of writing:

- **User consent to spend external model quota** — not given for Task 1. Required
  before Task 2 runs any real session.
- **codex (Harness B) model identity/tier** — UNKNOWN; pinning a model needs a
  session (`codex exec -m <model>`), which Task 1 must not run.
- **Token/cost usage telemetry** — UNKNOWN for both Harnesses; would require a
  real session.

Therefore the report stays pending. CLI simulation does not count as a completed
live pilot, and no acceptance criterion may be marked passed until real sessions
exist.

## What Task 1 established (prerequisites, observed)

- Two Harnesses present: Harness A = this Trae IDE session (observed model label
  `DeepSeek-V4.1-Flash`); Harness B = `codex` CLI `C:\nvm4w\nodejs\codex.ps1`,
  `codex-cli 0.160.0` (responds to `--version`). Observed absence:
  claude / gemini / aider / cursor-agent / opencode.
- Host: Windows / PowerShell 7; `python` 3.13.5; `git version 2.45.1.windows.1`.
- CLI entry point = `python d:\Code\agent-workflow\scripts\ai-workflow\main.py`
  (`--help` exit 0; `python -m ai-workflow` does **not** work). `init` / `start`
  produce `workflow_version: 2` by default (verified in a disposable temp target,
  then removed).
- Two observable tasks defined with commands and expected outputs recorded before
  model work (runbook §3–4); fixture baseline reproduced locally:
  `python demo.py` → `initial=1 / configured=2 / actual=1` (bug confirmed).
- Role prompts, clean-context receiving prompt, measurement fields and protocol
  prepared (runbook §5–6).

See [runbook.md](runbook.md) §1 for the full probe table.

## Session records

None. No real session has been run, so there are no Task / Role / Model / Harness /
Start–end / Tool activity / Usage / artifacts / repeated-exploration /
targeted-verification / outcome rows to report. Every such field would be
UNKNOWN — do not fill it in speculatively.

## Findings

None yet. Findings, anchor audits, correctness/rework and effort data are produced
by Task 2 from actual session outputs.

## Practical limits recorded now

- Tool-call counts alone do not establish cost savings.
- Unavailable token/cost data stay `UNKNOWN`; no fabricated savings percentage.
- A run without the required actual model pairing or the cross-Harness switch is
  an unmet prerequisite, not a successful simulated outcome.
- Any needed fixes become separate follow-up Tickets, not hidden scope growth.

## Next step (Task 2)

1. Obtain the user's consent to spend external model quota.
2. Follow [runbook.md](runbook.md) to run the real role sessions in the disposable
   target, crossing Harnesses on the planned handoff, and persist every raw output.
3. Audit pivotal anchors; recompute expected vs actual for both tasks.
4. Replace this pending report with the measured report, or — if access is still
   missing — keep it pending with the blocker above preserved.