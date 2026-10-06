# 07: Release the complete workflow contract without fabricating v1 compliance

Ticket ID: SCOUT-007
Type: task
Status: ready-for-agent
Blocked by: 06
Parent: [spec](../spec.md)
Plan: [Implementation plan](../../../docs/superpowers/plans/2026-10-07-scout-07.md)

## What to build

New installations and Tickets use the complete v2 contract, while existing
Tickets retain their historical version until deliberately upgraded. Adoption
and upgrade show missing reconstruction work instead of inventing passes.

## Scope and ownership

Own the release version/defaults, install/start/adopt/upgrade compatibility,
upgrade-ticket command, complete user documentation, version-conditioned
Protocol descriptions, and installed-target lifecycle tests. Preserve source
references and user content. Incorporate 01–06 before switching the default.

## Acceptance criteria

- [ ] New starts use v2, schema version 1, and the complete report/plan/review
  contracts. Scaffolds and pending gates are not marked completed.
- [ ] Protocol upgrade updates installed rules without silently bumping existing
  Tickets. v1 validation/mutation remains available; future versions reject.
- [ ] upgrade-ticket explicitly converts an active interpretable v1 Ticket,
  retaining Phase, sources, Evidence rounds, counters/history, and unknown fields.
- [ ] Missing audit bindings, registered Plan, or Review appear as blockers
  with senior reconstruction next action; no sufficiency or pass is fabricated.
- [ ] A senior reconstruction can supply current contracts and resume from the
  retained phase without inventing earlier phases or rewriting completed tasks.
- [ ] Historical done Tickets remain v1. Repeating upgrade is idempotent;
  uninterpretable State is unchanged with a clear error.
- [ ] Adopted Tickets cannot execute until continuation_safe is confirmed;
  incomplete adoption cannot bypass the check by phase/route manipulation.
- [ ] Installation, managed blocks, Skills and reruns remain idempotent and
  preserve user documents and references. Reviewer is installed with other roles.
- [ ] Temporary-target lifecycle runs through Scout, insufficient follow-up,
  audit, Plan, escalation/clear, execution, failed review/rework, pass, resume,
  and done with validation clean at eligible boundaries.
- [ ] README, baseline spec pointers, quickstart, adoption and proposed ADR status
  reflect what actually shipped. Previously planned behavior is not called
  implemented until its corresponding checks pass.

## Verification

Install the kit into a temporary target and drive its public CLI end to end.
Cover current/old/future versions, half-complete and done v1 Tickets, repeat
upgrade, missing reconstruction data, source-reference preservation, unknown
fields, dirty adoption, and no user-content overwrite. Run the relevant suite
then the existing full stdlib CLI suite once before release completion.

## Escalation conditions

If old work cannot be interpreted safely, preserve it and route to senior
reconstruction. Do not solve a compatibility failure by adding fake audit/review
records or automatically relabelling every Ticket v2.

## Context

Spec decisions 1 and 8 and [R-06](../review-findings.md) define the release boundary.
The existing YAML/parser and repo-native ADRs remain in force.

## Comments

- 2026-10-07 — This is the v2 release/default switch; previous gate slices remain
  demoable through explicit fixtures while the shipped default stays v1.
