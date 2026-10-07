# Decision Scout and Structured Handoff: Ticket Index

Status: baseline delivered; follow-up pending
Type: index
Parent: [spec](spec.md)
Plan: [Delivery plan and shared interfaces](../../docs/superpowers/plans/2026-10-07-decision-scout-handoff.md)

The original implementation and SCOUT-008 live pilot are delivered, as the
append-only comments and report record. Per-issue historical labels remain as
recorded; the table below preserves the original dependency graph. Current
unstarted work is the [nine HARDEN follow-up tickets](../decision-scout-hardening/tickets.md),
with a [supplemental spec](../decision-scout-hardening/spec.md) and
[development plan](../../docs/superpowers/plans/2026-10-08-scout-hardening.md).

| Ticket | Blocked by | End-to-end outcome |
|---|---|---|
| [01 — Traceable Scout reports](issues/01-traceable-scout-reports.md) | None | An inexpensive Scout can leave a report a senior role can use directly. |
| [02 — Audit-bound Evidence Gate](issues/02-audit-bound-evidence-gate.md) | 01 | Version 2 rejects malformed or changed audited Evidence. |
| [03 — Registered execution contracts](issues/03-registered-execution-contracts.md) | 02 | An executor receives a registered bounded task with an explicit next index. |
| [04 — Effective escalation routing](issues/04-effective-escalation-routing.md) | 02 | Unresolved uncertainty stops execution and routes to a senior resolver. |
| [05 — Current review and rework](issues/05-current-review-and-rework.md) | 03, 04 | Only current passing review permits completion; repairs have a normal path. |
| [06 — Portable continuation brief](issues/06-portable-continuation-brief.md) | 05 | Another Harness can identify the exact task, artifacts, and continuation checks. |
| [07 — Safe installation and upgrade](issues/07-safe-installation-and-upgrade.md) | 06 | Complete v2 ships without silently promoting existing Tickets. |
| [08 — Live model/Harness pilot](issues/08-live-model-harness-pilot.md) | 07 | Real bug/feature handoffs produce observed quality and effort evidence. |

The original 01→08 sequence is complete. It no longer defines the delivery
frontier. New review findings and the distinct-model pilot are tracked separately;
follow the HARDEN index's real blockers and shared-file scheduling.

## Validation seam

Use public CLI commands and temporary repositories, following the existing dogfood
test pattern. Report quality also needs a receiving reader and the live pilot;
CLI checks alone cannot establish the truth or usefulness of model-generated facts.

## Comments

- 2026-10-07 — Added eight implementation plans and a common interface/dependency
  contract following the user's Superpowers planning request. All tasks remain unchecked.
- 2026-10-07 — Eight local Tickets created from the updated spec. Cheap scouting
  is first, later gates are explicit, and release compatibility precedes the live
  pilot. Ticket bodies carry implementation scope and acceptance criteria.
- 2026-10-07 — SCOUT-008 (live model/Harness pilot) **remains pending/blocked**.
  Task 2 was attempted; the required real role sessions and cross-Harness handoff
  cannot run because explicit user consent to spend the user's external model
  quota is still missing. No real session was launched, so no run records or
  findings exist and no acceptance criterion was checked. Cost-free availability
  probes re-verified unchanged. See
  [issues/08](issues/08-live-model-harness-pilot.md) and
  [pilot/report.md](pilot/report.md). No Ticket was flipped to done.
- 2026-10-07 — Implementation of SCOUT-001..008 is complete. 01–02 were
  fast-forward merged into `master` (`24228e2`); 03–08 live on branch
  `decision-scout-port` (not pushed, pending the user's merge decision). A
  branch-wide final review (spanning all 22 commits) found one load-bearing
  cross-Ticket defect: a Ticket in the normal `review` phase with the scaffold
  `review.verdict: pending` was reported by `validate` as "a verdict is recorded"
  and made `resume` exit 1, contradicting the same file's `reconstruction_problems`
  and STATE_SCHEMA. Fixed in `8c280d4` (one-line narrowing + two regression tests);
  scoped re-review resolved it and the full suite passed (309 tests, skipped=1).
  Every other review finding was triaged as safe-to-defer. SCOUT-008 remains
  pending/blocked (see above). Per-issue `Status:` lines and acceptance-criteria
  boxes were left unchanged: this tracker documents no terminal `Status` value for
  `Type: task` tickets, so none was invented.
- 2026-10-07 — SCOUT-008 **Task 2 executed, still pending.** Consent for external
  model spend was given (5-session cap, option A). Real Harness-A sessions ran in a
  disposable target: a cheap scout produced anchored evidence for the bug and the
  feature, and a senior session audited, decided and registered a Plan for both;
  both tickets reached `implementation` with clean `validate`. An independent
  anchor/runtime re-check found no wrong anchors. **AC 2 is unmet:** three attempts
  to drive Harness B (`codex-cli 0.160.0`) non-interactively were blocked by host
  session policy, so no cross-Harness handoff could be persisted. The
  executor/reviewer sessions were not run (budget exhausted). Real records archived
  at [pilot/bug](pilot/bug/) and [pilot/feature](pilot/feature/); report at
  [pilot/report.md](pilot/report.md). No acceptance criterion was checked.
- 2026-10-07 — **SCOUT-008 complete.** Both pilot tickets (`PILOT-BUG-01`,
  `PILOT-FEAT-01`) reached `done` through real live sessions: Harness A (Trae;
  scout, senior audit/decision/Plan, executors) and Harness B (`codex-cli 0.160.0`,
  model `gpt-6.1-sol`, read-only) for the independent reviews. Persisted
  clean-context handoffs crossed A → B at both review boundaries; the feature
  review's `changes_requested` (unfilled handoff) was fixed via a recorded rework
  task and cleared by a scoped re-review (`pass`). The host codex policy block
  was resolved with `-c windows.sandbox="unelevated"` (86 logged commands green
  across the three successful receiver sessions). Observed friction: byte-exact
  v2 gate vs `core.autocrlf=true` (required `set-gate` re-attestation; archived
  audits needed byte-form recovery). Budget 5 (first cap) + 10 (raised cap)
  sessions; 205,882 codex tokens measured, Trae-side UNKNOWN. All ACs checked
  with notes in [issues/08](issues/08-live-model-harness-pilot.md); records:
  [pilot/report.md](pilot/report.md), [pilot/bug](pilot/bug/),
  [pilot/feature](pilot/feature/), [pilot/logs](pilot/logs/). Kit commit not
  pushed.

- 2026-10-08 — Updated the current overview to delivered baseline and linked HARDEN-001–009. Earlier pending/completion comments remain historical. No original issue was reopened, relabelled or resolved by this documentation change.
