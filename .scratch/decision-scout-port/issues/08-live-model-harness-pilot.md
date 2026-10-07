# 08: Evaluate real inexpensive Scout and cross-Harness handoffs

Ticket ID: SCOUT-008
Type: task
Status: ready-for-agent
Blocked by: 07
Parent: [spec](../spec.md)
Plan: [Implementation plan](../../../docs/superpowers/plans/2026-10-07-scout-08.md)

Pilot status (observed, 2026-10-07): **pending** — consent was given and real
Harness-A scout and senior sessions ran for both tasks (evidence, audit, decision
and a registered Plan), but the required cross-Harness handoff could not be
persisted because the `codex` CLI (Harness B) is blocked by host session policy;
the executor/reviewer sessions were not run (session budget exhausted). See
[pilot/runbook.md](../pilot/runbook.md) and [pilot/report.md](../pilot/report.md).
No acceptance criterion below is marked passed. Real records are archived under
[pilot/bug/](../pilot/bug/) and [pilot/feature/](../pilot/feature/).

## What to build

Produce an observed pilot report on one bug and one small feature showing whether
inexpensive scouting and structured handoff let senior roles decide with less
repeated exploration and acceptable rework across two actual Harnesses.

## Scope and ownership

Own pilot selection, manual run instructions, real reports/handoffs, measurement
record, and resulting improvement recommendations. Use a disposable target or
explicitly selected bounded repository tasks; no external publication, automatic
model launcher, or global configuration edits are part of this Ticket.

## Acceptance criteria

- [ ] One reproducible bug and one small feature use actual inexpensive Scout
  sessions, senior decision sessions, and executor/independent review sessions.
- [ ] At least one persisted handoff crosses two available actual Harnesses;
  receiving contexts do not inherit the sender's conversation.
- [ ] Evidence contains verified file/line/symbol anchors, DQ/F references,
  method/scope, UNKNOWN handling, and precise handoff; pivotal anchors are checked.
- [ ] Record which investigations the senior role repeated, which rereads were
  targeted verification, report gaps, clarification/escalation, and rework.
- [ ] Record models/Harnesses, elapsed time, role-level tool activity, and available
  token/cost data. Missing usage data is UNKNOWN; no fabricated savings percentage.
- [ ] Assess report usefulness and correctness separately from CLI validation.
  Report any need to adjust task size, Scout instructions, or model defaults.
- [ ] If required tools/models/Harness access is unavailable, record the missing
  condition and keep this Ticket pending/blocked. CLI simulation does not count
  as a completed live pilot.
- [ ] Publish the pilot record locally with source-artifact links and concrete
  findings. Further fixes become separate Tickets rather than hidden scope growth.

## Verification

Review actual session outputs, anchors and accepted changes for both tasks.
The pilot can report unsuccessful outcomes honestly; completing the measurement
does not require proving a fixed savings target. A run without the required
actual model pairing or Harness switch cannot satisfy this Ticket.

## Escalation conditions

Missing access, task ambiguity, or a correctness problem is recorded explicitly.
Do not purchase services or send messages to other chats/users automatically to
manufacture a completed pilot.

## Comments

- 2026-10-07 — Manual acceptance is separate from automated lifecycle tests so
  the intended benefit is judged from actual model work, not phase counts.
- 2026-10-07 — Task 1 (runbook + prerequisites) done; full task report at
  `.superpowers/sdd/2026-10-07-scout-08/task-1-report.md`. Observed: Harness A =
  this Trae session (model label `DeepSeek-V4.1-Flash`); Harness B = `codex` CLI
  `C:\nvm4w\nodejs\codex.ps1` (`codex-cli 0.160.0`); absent: claude / gemini /
  aider / cursor-agent / opencode. Host `python` 3.13.5, `git 2.45.1.windows.1`,
  CLI entry point `scripts/ai-workflow/main.py` (`--help` exit 0; `init`/`start`
  default to `workflow_version: 2`). No real model session was launched (only
  availability probes). Pilot stays pending on explicit user consent to spend
  external model quota; blocker recorded in [pilot/report.md](../pilot/report.md).
- 2026-10-07 — **Task 2 attempted; still PENDING/BLOCKED.** Task 2 Steps 1–2 need
  actual Scout + senior + executor + independent-review sessions and a handoff
  crossing two **real** Harnesses. The binding precondition — **explicit user
  consent to spend the user's external model quota/credentials** — is still
  **missing**, so no real session was launched and **no run records or findings
  exist**. Note the blocker is an **authorization** constraint (missing consent),
  not missing access: the models, tools and two Harnesses are available in
  principle, so AC 7's "access unavailable" condition does not technically apply.
  The precise basis for staying pending is **plan Task 2 Step 5** ("If
  prerequisites were missing, preserve pending status and blocker"); AC 7 is only
  a result-consistency cross-reference (a run without the required actual model
  pairing cannot satisfy this Ticket). The sanctioned result is to preserve pending
  status and the blocker rather than simulate. `.scratch/decision-scout-port/pilot/bug/`
  and `.../feature/` were deliberately **not** created (no actual records to copy;
  placeholder content would be fabrication). Cost-free availability probes were
  re-verified unchanged (`python` 3.13.5, `git` 2.45.1.windows.1, `ai-workflow
  --help` exit 0, `codex-cli 0.160.0`). Binding ruling recorded: do not launch,
  authenticate, or invoke any real/paid model session without consent — only
  availability probes. Commit used is `ai-workflow(SCOUT-008): record live pilot
  blocker (pending)` (the plan's "record live model and harness findings" wording
  does not apply because no runs produce no findings). Status stays as-is; **no
  acceptance criterion was checked**. Full report:
  `.superpowers/sdd/2026-10-07-scout-08/task-2-report.md`.
- 2026-10-07 — **Task 2 executed (partially).** User consent for external model
  spend was given (cap: 5 sessions, ~3 min each, option A). Real **Harness-A**
  sessions ran in a disposable target (`%TEMP%\scout008-target`, two isolated
  branches): a cheap **scout** wrote anchored `evidence.md` for both the bug and
  the feature (`0504a25`, `d5234df`), and a senior session audited sufficiency,
  wrote `decision.md`/`plan.md` and recorded `gate=sufficient` round 1 for both
  (`a947051`, `b856779`). Both tickets reached `implementation` with a registered
  Plan and clean `validate`. An independent re-check of every pivotal anchor
  (`service.py:1-6`, `demo.py:1-18`) and the runtime claim (`python demo.py` →
  `initial=1/configured=2/actual=1`, exit 0) found **no wrong anchors**. However
  **AC 2 (cross-Harness handoff) is unmet**: three attempts to drive Harness B
  (`codex-cli 0.160.0`) non-interactively were **blocked by host session policy**
  (project trust allowlist excludes the temp target; `-c approval_policy`/trust
  overrides failed). The executor and independent-reviewer sessions were **not
  run** — the 5-session budget was exhausted by the scout + senior + 3 blocked
  codex attempts. Observed friction: a byte-exact v2 gate plus `core.autocrlf=true`
  forced `set-gate` re-attestation after branch switches. Result: **stays pending**;
  no AC passed. Real records archived at [pilot/bug/](../pilot/bug/) and
  [pilot/feature/](../pilot/feature/); full report at [pilot/report.md](../pilot/report.md).
