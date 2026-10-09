# 11: Isolated reviewer verification and guarded publication

Ticket ID: HARDEN-011
Type: task
Status: planned — awaiting plan review and execution method
Blocked by: 10
Parent: [C10 reviewer isolation](../spec.md#c10--isolated-reviewer-verification-and-guarded-publication-harden-011)
Source findings: O4; [disposition](../review-disposition.md)
Plan: [development plan](../../../docs/superpowers/plans/2026-10-09-harden-11.md);
this Ticket is not a registered execution contract.

## What to build

Run reviewer probes and verification in an identified disposable snapshot,
enforce denial of writes to live source/tests/fixtures/Git, and publish only the
reviewer's exact result after checking that its live baseline is still current.

## Evidence and attribution limits

The user reported temporary test injection followed by byte-exact restoration
in another source tree. This repository contains no InspectionPage.test.tsx,
and no responsible process has been definitively identified. Do not attribute
the event to a particular reviewer. The observed design gap here is narrower:
reviewer instructions name production code only, independent context has no
filesystem boundary, and final drift checks cannot reveal restored writes.

## Scope and ownership

Own the bounded snapshot/preflight/publication mechanism selected in planning;
its Review-report validation and public-command/installer regressions; Protocol,
Roles, Artifact contracts, reviewer entry point, review template and supported
adapter instructions. Protocol owns permissions/procedure, ARTIFACTS owns report
provenance; Skills remain pointers. Freeze exact source files/API before writing.
HARDEN-010 supplies trustworthy live drift checks. No new role, orchestration
service, general permission system, global config or retroactive pilot rewrite.
Only one writer may edit shared protocol/Review files at a time.

## Acceptance criteria

- [ ] Snapshot captures full reviewed commit, independent Git metadata,
      separate live/snapshot content identities, Plan and input raw-byte hashes;
      relevant live dirty code cannot be omitted to obtain approval.
- [ ] A supported per-session boundary actually denies verifier writes to live
      source/tests/fixtures/config/Git. Controlled protected-sentinel tests use
      disposable repositories; they never attempt a write to real source.
- [ ] Snapshot probes/caches may be written in declared scope. Copy-only,
      prompt-only and writable shared-Git worktree arrangements cannot claim
      enforcement. An unavailable boundary reports a blocker and no passing
      publication; no automatic permission weakening or model-session retries.
- [ ] Baseline acceptance runs and probe-modified runs are distinguished.
      Report actual commands, directory/scope, exit/results, failures, probe
      paths/changes, residual snapshot changes and verification limits.
- [ ] The Reviewer remains author of the technical verdict. A guarded separate
      publisher may write only Review/State/Handoff through public commands;
      publication neither supplies a new verdict nor repairs/advances source.
- [ ] Live code, Plan or input drift before publication rejects it without a
      new verdict or overwriting existing workflow records. Fresh review is
      required; exact Ticket-record exemptions stay unchanged.
- [ ] New report provenance is checked without invalidating historical Review
      artifacts/bindings or inventing past isolation evidence. No hash/schema
      version change; v1 behavior remains compatible.
- [ ] Automated snapshot/publication regressions and installation/lifecycle
      checks pass. Record a real host restriction/denial check for each claimed
      supported adapter; mocked launch success alone is insufficient.

## Verification

Use a disposable live/snapshot pair to verify denial, allowed probe writes,
shared-metadata rejection, identity mismatches, publication refusal and byte
preservation. Keep raw artifact identities intact across clone/checkout. Record
unsupported environments explicitly. Helper tests do not prove a Harness host
restriction. Any live model session additionally needs explicitly authorized
available budget; this Ticket creation authorizes none.

## Escalation conditions

Planning must select a real enforceable boundary for the target host. If none
is available, report unsupported/blocked and the missing capability; do not
substitute a prompt or end-of-run hash check. Freeze publication failure/atomicity
and historical report compatibility before implementation.

## Comments

- 2026-10-09 — Specification and authoritative procedure supplemented. Runtime
  isolation/report/publication mechanisms are not implemented by this document.
- 2026-10-09 — Development plan saved with exact file ownership, interfaces,
  regression assertions and verification commands. Runtime acceptance remains
  pending; planning performs no implementation or model session.
