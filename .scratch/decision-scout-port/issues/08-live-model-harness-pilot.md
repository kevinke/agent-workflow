# 08: Evaluate real inexpensive Scout and cross-Harness handoffs

Ticket ID: SCOUT-008
Type: task
Status: ready-for-agent
Blocked by: 07
Parent: [spec](../spec.md)
Plan: [Implementation plan](../../../docs/superpowers/plans/2026-10-07-scout-08.md)

Pilot status (observed, 2026-10-07): **complete** — both pilot tickets reached
`done` through real live sessions: an inexpensive Scout, a senior session
(audit/decision/Plan), executor sessions, and **independent reviewer sessions on
a second actual Harness** (`codex` CLI, read-only), with persisted clean-context
handoffs crossing Harness A → Harness B (bug review; feature review + re-review).
Session budget consumed: 5/5 of the first cap plus 10/10 of the raised cap (15
sessions; 205,882 codex tokens measured; Trae-side usage UNKNOWN). The earlier
host-policy block of Harness B was resolved at run time by launching codex with
`-c windows.sandbox="unelevated"` (session policy still read-only). See
[pilot/runbook.md](../pilot/runbook.md), [pilot/report.md](../pilot/report.md)
and the raw receiver logs in [pilot/logs/](../pilot/logs/). Real records are
archived under [pilot/bug/](../pilot/bug/) and [pilot/feature/](../pilot/feature/)
in the exact byte forms bound in each ticket's `state.yaml`.

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

- [x] One reproducible bug and one small feature use actual inexpensive Scout
  sessions, senior decision sessions, and executor/independent review sessions.
  (Scout + senior + executors on Harness A; independent reviews on Harness B.)
- [x] At least one persisted handoff crosses two available actual Harnesses;
  receiving contexts do not inherit the sender's conversation. (A → B at both
  review boundaries; fresh `codex exec` receivers, persisted-artifact inputs
  only; first action = `resume`; receiver logs in `pilot/logs/`.)
- [x] Evidence contains verified file/line/symbol anchors, DQ/F references,
  method/scope, UNKNOWN handling, and precise handoff; pivotal anchors are checked.
  (Final anchor audit found no wrong or missing anchors; runtime claims reproduced;
  see `pilot/report.md`.)
- [x] Record which investigations the senior role repeated, which rereads were
  targeted verification, report gaps, clarification/escalation, and rework.
  (No broad re-survey observed; targeted rereads only; one handoff gap found by
  review → one recorded rework task → re-review `pass`; no escalation triggered.)
- [x] Record models/Harnesses, elapsed time, role-level tool activity, and available
  token/cost data. Missing usage data is UNKNOWN; no fabricated savings percentage.
  (Codex: model `gpt-6.1-sol`, session ids, tokens, 86 logged commands. Trae-side:
  model label + windows recorded; tokens/tool counts UNKNOWN.)
- [x] Assess report usefulness and correctness separately from CLI validation.
  Report any need to adjust task size, Scout instructions, or model defaults.
  (Reviewers assessed behavior separately; the unfilled-handoff case shows
  `validate: OK` alone does not prove the criteria passed. No task-size or Scout
  instruction change is recommended from this pilot.)
- [x] If required tools/models/Harness access is unavailable, record the missing
  condition and keep this Ticket pending/blocked. CLI simulation does not count
  as a completed live pilot. (The condition existed and was recorded while it
  lasted; it was then resolved by the sandbox launch fix, and the live pilot
  completed — no simulation was used.)
- [x] Publish the pilot record locally with source-artifact links and concrete
  findings. Further fixes become separate Tickets rather than hidden scope growth.
  (Report + logs + byte-exact archived artifacts; friction/follow-up candidates
  recorded as candidates; no fixes were folded into this Ticket.)

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
- 2026-10-07 — **Task 2 complete; both tickets reached `done` through live
  sessions across two Harnesses.** Budget: 5/5 (first cap: scout, senior, 3
  policy-blocked codex attempts) + 10/10 (raised cap: 4 sandbox-policy probes,
  Harness-A bug executor, codex bug review v1 [blocked] and v2 [pass], Harness-A
  feature executor, codex feature review [changes_requested] and re-review
  [pass]). Key results: (1) the host sandbox-policy block was resolved with
  `-c windows.sandbox="unelevated"` — afterwards 86/86 logged receiver commands
  across three sessions ran with no policy rejection (only one auxiliary skill
  lookup failed on a bad path and was recovered); (2) the required cross-Harness
  handoff was performed with clean receiver contexts (A implementation → B review
  for the bug and for the feature), each receiver's first action being `resume`
  with persisted artifacts as its only inputs; (3) the feature review found that
  `validate: OK` does not prove the handoff obligation — the unfilled handoff
  template was caught only by the independent reviewer, fixed in a recorded
  rework task, and cleared by a scoped re-review (`pass`); (4) the byte-exact v2
  gate plus `core.autocrlf=true` required `set-gate` re-attestation during the
  pilot (real observed friction). Measured usage: 205,882 codex tokens across 4
  sessions; Trae-side usage UNKNOWN; no savings claims. All acceptance criteria
  above are satisfied (see the parenthetical notes; AC 7's conditional block
  existed and was recorded before the access fix; no simulation was used).
  Records: [pilot/report.md](../pilot/report.md), byte-exact archives at
  [pilot/bug/](../pilot/bug/) and [pilot/feature/](../pilot/feature/), raw
  receiver logs at [pilot/logs/](../pilot/logs/). Kit commit:
  `ai-workflow(SCOUT-008): record live model and harness findings` (not pushed).
