# Decision Scout and Structured Handoff: Ticket Index

Status: ready-for-agent
Type: index
Parent: [spec](spec.md)
Plan: [Delivery plan and shared interfaces](../../docs/superpowers/plans/2026-10-07-decision-scout-handoff.md)

Each implementation Ticket is a separate file under issues. Work blockers-first;
all Tickets are unstarted. Each Ticket now links its development plan, covering
exact files, interfaces, verification and commits. Planning is complete;
implementation has not started. Ticket labels do not imply existing support.

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

The immediate frontier is 01. After 02, 03 and 04 have independent behavioral
dependencies; their implementations may touch shared mutation code and should
still follow the repo's writing/concurrency rules. Dependency independence does
not authorise parallel writers.

01 is intentionally usable before the stronger CLI release. Tickets 02–06
exercise explicit v2 test fixtures while the shipped default stays v1; 07 switches
new installations and new Tickets to the complete v2 contract. 08 is a manual
acceptance Ticket, distinct from automated CLI regression coverage.

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
