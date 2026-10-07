# 08: Evaluate real inexpensive Scout and cross-Harness handoffs

Ticket ID: SCOUT-008
Type: task
Status: ready-for-agent
Blocked by: 07
Parent: [spec](../spec.md)
Plan: [Implementation plan](../../../docs/superpowers/plans/2026-10-07-scout-08.md)

Pilot status (observed, 2026-10-07): **pending** — Task 1 prepared the runbook and
recorded prerequisites; the report remains pending and **no real model session has
been run** (external-budget ruling). See [pilot/runbook.md](../pilot/runbook.md)
and [pilot/report.md](../pilot/report.md). No acceptance criterion below is marked
passed.

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
  availability probes). Pilot stays pending pending explicit user consent to spend
  external model quota; blocker recorded in [pilot/report.md](../pilot/report.md).
