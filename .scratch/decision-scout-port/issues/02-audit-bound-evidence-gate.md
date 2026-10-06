# 02: Bind the Evidence Gate to the audited Scout Report

Ticket ID: SCOUT-002
Type: task
Status: ready-for-agent
Blocked by: 01
Parent: [spec](../spec.md)
Plan: [Implementation plan](../../../docs/superpowers/plans/2026-10-07-scout-02.md)

## What to build

For an explicit v2 Ticket, the CLI rejects a structurally incomplete Scout
Report and prevents a senior audit of one report from being reused after that
report changes. A valid report can still contain unknowns and be audited as
insufficient; the auditor judges their significance.

## Scope and ownership

Own Evidence/audit structural validation, set-gate binding, transition checks,
version-aware validation, corresponding protocol/schema descriptions, CLI
diagnostics, and public-command regressions. Reuse the existing CLI and
restricted YAML subset. Preserve the current counter-consistency source edits.

Treat version 2 as an explicit test-fixture contract until 07 releases it.
The shipped default remains v1. Support v1 and v2 deliberately and reject
unknown future versions. This Ticket does not implement automatic dispatch.

## Acceptance criteria

- [ ] A v2 report lacking required metadata, DQ/F IDs, valid tags, source
  anchors, or resolvable report references fails structural validation.
- [ ] Template scaffolds and placeholder-only reports do not satisfy the gate.
- [ ] set-gate records the audited round, Evidence SHA-256 and audit SHA-256 only when a
  structured report and non-placeholder audit exist; it requires evidence_audit
  or a documented senior escalation-resolution audit.
- [ ] Changing Evidence or its audit after a sufficient verdict makes its binding stale;
  validate and decisionward advances report the same blocker.
- [ ] An insufficient report can take the existing follow-up loop; new rounds
  preserve earlier finding references and need a new audit.
- [ ] The audit can justify noncritical UNKNOWNs without inventing facts;
  structural checks do not claim to establish factual truth or risk sufficiency.
- [ ] Rejected mutations leave State unchanged; diagnostics name the missing
  report field or stale binding and the expected next action.
- [ ] v1 command behavior remains compatible, unknown fields survive, and no
  template workflow-version default is switched prematurely.

## Verification

Drive the real CLI against temporary repositories: insufficient follow-up,
sufficient current audit, malformed/missing anchors and references, empty audit,
report changed after audit, wrong-phase verdict, supported/unsupported versions,
and preservation on rejection. Verify observable State/output/exit status.

## Escalation conditions

Escalate factual or architectural questions to the senior role. Keep machine
validation limited to structure, identity, and protocol conditions; do not build
a probabilistic truth checker or introduce new dependencies.

## Context

Spec decisions 1–3 and [R-05](../review-findings.md) are authoritative. The four
audit questions stay intact; richer Evidence is what they evaluate.

## Comments

- 2026-10-07 — First v2 gate slice, after the Scout contract is usable.
