# 06: Resume a Ticket in another Harness from a portable continuation brief

Ticket ID: SCOUT-006
Type: task
Status: ready-for-agent
Blocked by: 05
Parent: [spec](../spec.md)
Plan: [Implementation plan](../../../docs/superpowers/plans/2026-10-07-scout-06.md)

## What to build

A receiving Agent can use a read-only CLI brief and referenced artifacts to
identify its exact next task, relevant evidence, review identity, and continuation
checks without the departing Agent's chat history.

## Scope and ownership

Own resume command/output, Handoff additions, model/role routing clarification,
thin Harness adapter guidance, and CLI continuation tests. It consumes the
contracts and gates delivered by 01–05; it does not create a dispatcher.

## Acceptance criteria

- [ ] resume prints Ticket, Phase, Status, Gate, escalation, next role/action/task,
  Git identity/dirty state, artifact references/digests, validation findings,
  and explicit blockers or freshness checks.
- [ ] It is read-only, including updated_at and Claims, and references reports
  instead of pasting their full contents.
- [ ] Handoff records relevant drift, verification limits, artifact identity,
  what not to repeat, and the exact recommended next action.
- [ ] Evidence on an older commit prompts relevance assessment of its anchors;
  it is not automatically classified as false. Review freshness follows 05.
- [ ] v1 Tickets produce usable continuation output and explicit notices for
  missing newer contracts rather than invented gates or migration success.
- [ ] Model tiers are defaults mapped by each Harness. Hard investigation or
  implementation can use senior capability; tool/environment gaps escalate.
- [ ] Logical phases may share a session, Review retains independent context,
  and adapters support manual switching without assuming subagent tools.
- [ ] Independent simulated sender/receiver sessions can continue the CLI
  lifecycle from persisted State and artifacts; simulation is labelled as such.

## Verification

Compare State and repository files before/after resume. Use two independent
processes to demonstrate continuation with no chat, a missing artifact, stale
audit, relevant/irrelevant repository drift, an unresolved escalation, and v1
notices. Actual model/Harness performance is verified in 08.

## Escalation conditions

Do not turn advisory Claims into locks or invent an automatic launcher. The
receiver must report missing tools or material unresolved facts rather than
blindly execute the brief.

## Context

Spec decision 7 defines the continuation behavior. Existing repo-native adapters
stay consistent with ADR-0001; global model policy is outside this Ticket.

## Comments

- 2026-10-07 — Continuation exposes the complete gate/contract state rather than
  a second authority duplicating State.
