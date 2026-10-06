# 01: Produce traceable Decision Scout reports

Ticket ID: SCOUT-001
Type: task
Status: ready-for-agent
Blocked by: None (can start immediately)
Parent: [spec](../spec.md)
Plan: [Implementation plan](../../../docs/superpowers/plans/2026-10-07-scout-01.md)

## What to build

An inexpensive Scout can take an engineering request, perform bounded repository
research, and leave Evidence that a senior role can use for decisions with
targeted verification. This is the first usable increment and works with v1.
It does not wait for later review or orchestration changes.

## Scope and ownership

Own the Scout report contract/template, relevant Protocol and role instructions,
thin Scout/auditor Skill entry points, and bug/feature example reports. The
shared Workflow Protocol owns the rules; Skills point at it. Keep the existing
Evidence artifact, rounds, and Migration Notice. Follow spec decisions 1–3.

The examples must be based on a small reproducible repository scenario with real
anchors, rather than fictional production findings. Preserve existing source
edits and historical documents; this Ticket does not change production CLI code.

## Acceptance criteria

- [ ] Required report sections are Metadata, Decision Questions, Findings,
  Unknowns, and Handoff; task-specific detail is conditional, not a fixed quota.
- [ ] Metadata records observed revision, relevant dirty changes, time, Ticket,
  report format, and Scout provenance. Task type stays report metadata.
- [ ] Each important finding has stable ID, tag, statement, DQ references,
  sources, verification method, and limits. Code findings carry file/line/symbol
  or a justified key/record anchor; runtime findings carry command/input/result.
- [ ] Static inspection and observed runtime behavior are distinct; negative
  searches state scope; INFERENCE cites its basis; UNKNOWN states decision impact.
- [ ] Scouts can draft DQs, escalate architectural ambiguity, and stop with
  explicit gaps. Critical UNKNOWN does not imply a sufficient Evidence Gate.
- [ ] Bug and feature examples demonstrate traceability, a scoped negative
  search, an unresolved unknown, and retained references across follow-up rounds.
- [ ] An independent receiving reader can locate the pivotal claims directly
  without doing a general survey. Record that check and any targeted rereads.
- [ ] The auditor's existing four questions accommodate the richer report.
  Scout never records its own sufficient verdict or final design.
- [ ] Instructions keep report readiness separate from audit sufficiency,
  preserve v1 State compatibility, and do not require confidence scores.

## Verification

Walk one bug and one feature request through the Scout instructions using the
reproducible examples. Check each pivotal anchor against its observed revision;
have a receiving reader answer the stated DQs from the report. Structural
examples do not establish savings from actual model use; that belongs to 08.

## Escalation conditions

Escalate if report structure requires a new State phase or a final architecture
decision. Neither is authorised by this Ticket. A failed reproduction stays
explicitly unknown rather than being filled with a plausible root cause.

## Context

[R-01 and earlier-analysis assessment](../review-findings.md) describe the gap.
The [original proposal](../original-proposal.md) and
[fit analysis](../fit-analysis.md) are verbatim historical sources, not the new
authoritative contract. Use the parent spec to resolve disagreements.

## Comments

- 2026-10-07 — Created as the immediate frontier; user prioritised inexpensive
  scouting and structured, precisely anchored facts.
- 2026-10-07 — Task 1 implemented (branch ticket-01-traceable-scout). Canonical
  Scout Report grammar written into .ai/workflow/ARTIFACTS.md (Evidence
  format_version=1: Metadata with observed_commit/dirty_changes/provenance,
  Decision Questions DQ-01…, Findings F-01 [FACT|INFERENCE|UNKNOWN] with
  anchored Sources/Method/Scope, Unknowns, Handoff); templates/evidence.md and
  evidence-audit.md updated (rounds and Migration Notice preserved; audit keeps
  exactly the four sufficiency questions plus Metadata with evidence_sha256);
  PROTOCOL.md gains a scouting/auditing section; ROLES.md scout outputs/rules
  updated. Thin Skills (repo-scout, evidence-auditor) point at the contract —
  DQ drafting, architectural escalation, temporary diagnostics, stop rules;
  no State fields or business-rule copies added. Fixture
  .ai/workflow/examples/scout-fixture/{service.py,demo.py} runs clean:
  `python demo.py` prints initial=1, configured=2, actual=1, exit 0. Worked
  examples scout-bug.md (ready-for-audit) and scout-feature.md (partial with a
  critical UNKNOWN; only the auditor can open the Gate) anchor to observed
  commit bceba0fb81f6dad3e2c7dfb6fe4c89b61e7bbe7e with the fixture as dirty
  changes; receiving-reader check located every pivotal claim directly without
  a general survey. Verification: test_skills.py 4 tests OK, test_start.py 6
  tests OK, test_validate.py 18 tests OK. Commit:
  ai-workflow(SCOUT-001): add traceable Scout report contract.
