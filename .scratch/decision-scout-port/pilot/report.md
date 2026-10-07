# Pilot Report — Measured Live Model/Harness Handoff (SCOUT-008)

Status: **PENDING / BLOCKED — no real model session run.**
Date prepared: 2026-10-07 (Task 1). Task 2 attempted: 2026-10-07. Runs performed:
**none**.

Procedure: [runbook.md](runbook.md). Plan Task 2, spec Testing Decisions, issue
[08-live-model-harness-pilot.md](../issues/08-live-model-harness-pilot.md).

## Task 2 outcome (attempted, still pending)

Task 2 (plan `2026-10-07-scout-08.md`, Steps 1–2) requires **actual** inexpensive
Scout + senior + executor + independent-review sessions and a handoff crossing two
**real** Harnesses. Task 2 was **attempted** on 2026-10-07 and could **not proceed**
because the binding prerequisite — **explicit user consent to spend the user's
external model quota/credentials** — is still **missing**.

Binding ruling (quoted verbatim from [runbook.md](runbook.md) §0; governs this
outcome):

> No task may launch a real model session that spends the user's external
> quota/credentials without the user's consent. Task 1 must ONLY *probe*
> availability and record it — e.g. run version/help checks like `codex --version`,
> `git --version`, verify `ai-workflow --help` works. It must NOT authenticate or
> run any paid/real model session.

Consequence: **no real role session was launched**, so there are **no run records
and no findings**. The precise basis for keeping this pending is **plan Task 2
Step 5** ("If prerequisites were missing, preserve pending status and blocker").
Note the blocker is an **authorization** constraint, not missing access: the
models, tools and two Harnesses are available in principle, so issue AC 7's
"access unavailable" condition does not technically apply. AC 7 is cited only as a
result-consistency cross-reference: a run without the required actual model pairing
cannot satisfy this Ticket, so it stays pending/blocked. The plan-sanctioned
result is to **preserve pending status and the blocker** rather
than fabricate runs. A pending outcome honestly recorded is the correct Task 2
result here — it is not a failed Task and not a simulated success. The plan's
"record live model and harness findings" commit wording was **not** used because no
real runs produce no findings; the commit is
`ai-workflow(SCOUT-008): record live pilot blocker (pending)`.

### Step-by-step Task 2 status

- **Step 1 (run bug through real role sessions):** NOT DONE — prerequisite
  (external-quota consent) missing.
- **Step 2 (run feature likewise):** NOT DONE — same prerequisite missing.
- **Step 3 (audit pivotal anchors / rerun verification):** NOT DONE — no runs to
  audit; nothing to recompute.
- **Step 4 (findings with practical limits):** only the practical limits below are
  recorded; **no** observed findings exist to report.
- **Step 5 (review completion evidence and commit):** prerequisites were missing →
  pending status and blocker preserved; commit is the pending-appropriate one.

## Explicit blocker (why this is pending, not passed)

The pilot requires **actual** inexpensive Scout, senior, executor and independent
review sessions plus at least one persisted handoff between two real Harnesses
(spec Testing Decisions; issue AC 1–2). Per the binding external-budget ruling
(runbook §0), no real model session that spends the user's external
quota/credentials may be launched without the user's explicit consent. No such
consent has been given, so **no real session was launched** and no run record
exists.

Concrete unmet prerequisite:

- **User consent to spend external model quota** — **not given**. Required before
  Task 2 can run any real session. **This is the blocker.**

Record-only data gaps (non-blocking — they fill measurement fields at run time,
they do not prevent the pilot from running once consent is given):

- **codex (Harness B) model identity/tier** — UNKNOWN; pinning a model needs a
  session (`codex exec -m <model>`), which the ruling forbids running now.
- **Token/cost usage telemetry** — UNKNOWN for both Harnesses; would require a real
  session.

Therefore the report stays pending. CLI simulation does not count as a completed
live pilot, and no acceptance criterion may be marked passed until real sessions
exist.

## No bug/feature record directories exist

Plan Task 2 expects `.scratch/decision-scout-port/pilot/bug/` and `.../feature/`
to hold **actual** copied State, Evidence, audit, decision, Plan, Progress,
Handoff and Review records. Because **no real session ran**, there are no actual
records to copy, so those directories were **deliberately not created**. Creating
them with placeholder or synthetic content would fabricate evidence and is
forbidden. They may only be created once consented real sessions produce real
records (runbook §7–8).

**Plan Files-list deviation (visible to a future auditor).** The plan's Task 2
Files list also says "Modify ... runbook.md" and "Create ... pilot/bug/ and
.../feature/". Under the pending branch of Step 5 — no real records exist to copy,
and the runbook needed no clarification — both were intentionally **not**
satisfied: `runbook.md` is unchanged and `bug/`/`feature/` were not created.

## Availability probes re-run in Task 2 (no paid session)

These zero-cost probes were re-run in Task 2 (2026-10-07); observed values are
**unchanged** from Task 1:

- `python --version` → `Python 3.13.5`
- `git --version` → `git version 2.45.1.windows.1`
- `python d:\Code\agent-workflow\scripts\ai-workflow\main.py --help` → usage
  printed (exit 0)
- `C:\nvm4w\nodejs\codex.ps1 --version` → `codex-cli 0.160.0`

No paid/real model session was launched; only these availability probes were run.

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

See [runbook.md](runbook.md) §1 for the full probe table. The two-Harness
prerequisite is met **in principle**, but it is not sufficient: a meaningful
Harness switch requires a real receiving session, which the ruling forbids without
consent.

## Session records

None. No real session has been run, so there are no Task / Role / Model / Harness /
Start–end / Tool activity / Usage / artifacts / repeated-exploration /
targeted-verification / outcome rows to report. Every such field would be
UNKNOWN — do not fill it in speculatively.

## Findings

**None.** Findings, anchor audits, correctness/rework and effort data require
actual session outputs, which do not exist. Do not invent tool counts, anchors, or
savings.

## Practical limits recorded now

- Tool-call counts alone do not establish cost savings.
- Unavailable token/cost data stay `UNKNOWN`; no fabricated savings percentage.
- A run without the required actual model pairing or the cross-Harness switch is
  an unmet prerequisite, not a successful simulated outcome.
- Structural validity is not proof that acceptance criteria passed.
- Any needed fixes become separate follow-up Tickets, not hidden scope growth.

## Next step (still Task 2, still blocked)

1. Obtain the user's explicit consent to spend external model quota.
2. Follow [runbook.md](runbook.md) to run the real role sessions in the disposable
   target, crossing Harnesses on the planned handoff, and persist every raw output.
3. Audit pivotal anchors; recompute expected vs actual for both tasks.
4. Replace this pending report with the measured report, or — if consent is still
   absent — keep it pending with the blocker above preserved.