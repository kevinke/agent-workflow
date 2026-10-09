# 11: Isolated reviewer verification and guarded publication

Ticket ID: HARDEN-011
Type: task
Status: complete (automated + real-host boundary) — branch `harden-011`, awaiting integration
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

- [x] Snapshot captures full reviewed commit, independent Git metadata,
      separate live/snapshot content identities, Plan and input raw-byte hashes;
      relevant live dirty code cannot be omitted to obtain approval.
- [x] A supported per-session boundary actually denies verifier writes to live
      source/tests/fixtures/config/Git. Controlled protected-sentinel tests use
      disposable repositories; they never attempt a write to real source.
- [x] Snapshot probes/caches may be written in declared scope. Copy-only,
      prompt-only and writable shared-Git worktree arrangements cannot claim
      enforcement. An unavailable boundary reports a blocker and no passing
      publication; no automatic permission weakening or model-session retries.
- [x] Baseline acceptance runs and probe-modified runs are distinguished.
      Report actual commands, directory/scope, exit/results, failures, probe
      paths/changes, residual snapshot changes and verification limits.
- [x] The Reviewer remains author of the technical verdict. A guarded separate
      publisher may write only Review/State/Handoff through public commands;
      publication neither supplies a new verdict nor repairs/advances source.
- [x] Live code, Plan or input drift before publication rejects it without a
      new verdict or overwriting existing workflow records. Fresh review is
      required; exact Ticket-record exemptions stay unchanged.
- [x] New report provenance is checked without invalidating historical Review
      artifacts/bindings or inventing past isolation evidence. No hash/schema
      version change; v1 behavior remains compatible.
- [x] Automated snapshot/publication regressions and installation/lifecycle
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

## Verification record

Implemented on branch `harden-011` from `95a1d34`. Task 1 `ceee3dc` with fixes
`778686f`, `081655d`, `3c45a26`; Task 2 `a9782c7` with fixes `2f7a9dc`,
`4cb1985`; Task 3 `5191b84` with fix `819f371`; Task 4 `019ea59` with fixes
`7720965`, `181a5db`; branch-level `e204749`, `3f0902c`, `7ea38fd`, `1a8367f`.
Every task was implemented by a fresh agent and independently reviewed with
mutation testing; two reviewer-proposed fixes were rejected after the controller
showed they could not work (an "untracked in-scope file" divergence is already
counted as drift by HARDEN-010; a live-HEAD concern was disproved for
revalidation, and the opposite turned out to be required at the publication
door).

Full suite, serial, on a clean tree at `1a8367f`: 488 tests collected; three
module groups of 98 (`OK (skipped=2)`, 212.559s), 211 (`OK (skipped=1)`,
228.864s) and 179 (`OK (skipped=1)`, 158.937s). The four skips are all
symlink-privilege legs — unprivileged `os.symlink` returns `WinError 1314` on
this host. No boundary leg skipped in this run: all six
`test_review_boundary.ReviewBoundaryTest` cases exercised the real
`linux-bwrap-v1` path.

Real-host restriction, measured rather than asserted: `review_boundary.preflight`
on a genuinely prepared context records `enforced: true`, `blocker: null`,
`bwrap_version: bubblewrap 0.9.0`, with a Windows coordinator driving WSL bubblewrap
through `wsl.exe --exec`; the publication fixture's own route on this host is
`linux-bwrap-v1 on this host`. `adapters/local-review.md` carries the denial table,
the writable scopes and the network refusal, citing committed tests and receipt
fields so a fresh checkout can resolve every claim.

End-to-end dogfood of the documented flow, performed by the whole-branch reviewer
in a throwaway repository: install the kit, advance a Ticket to `review`,
`prepare-review`, run a baseline and a probe run under the real boundary, fill the
candidate `## Isolation provenance` from the supervisor's own receipts, guarded
`set-review`, then `validate` / `resume` / `review -> done`. Attempting to cheat
the door was refused every time, with the reason named in the message: a run the
supervisor never recorded and a receipt borrowed from another context
(`receipt-absent`), a report citing 2 of the 3 recorded runs (`receipt-uncited`),
a report declaring no residual change over paths a receipt observed
(`residual-changes-erased`, including a probe note restored afterwards), a
hand-tampered snapshot (`snapshot-state-unexplained`), a `--allow-empty` commit
after preparation whose tree was byte-identical (`live-head-mismatch`), a second
publication from a consumed context (captured-input staleness), a baseline-only
run set (`run-kinds-indistinct`), and an isolated report pushed through the
ordinary `set-review --verdict`, which refuses because the reserved provenance
section would go unvalidated. Writes to the live tree and to `meta/` from inside a
sandboxed run were denied with the target bytes identical before and after, while a
snapshot edit made from inside the boundary was permitted *and* recorded, so the
report still had to declare it.

That dogfood also produced the last blocking findings, and they were documentation
rather than mechanism: the `checkpoint-handoff` role gate refused the publication
step its own skill later requires, and the shipped review template modelled a
single baseline run that publication refuses for lacking a probe. Both are fixed
and pinned, together with a guard message that named options the CLI rejects, an
adapter pointer into git-ignored working notes, installed documents pointing at
runbooks the installer never copies, an undocumented preparation-owner and an
undocumented fail-closed stray-artifact refusal.

Limits this Ticket deliberately leaves in place, stated in the protocol rather
than papered over: the publication lock is per review context, so two contexts
prepared for one Ticket are not serialised against each other and only the in-lock
identity recheck narrows that; `limits`, a run's inner commands and a probe's
before/after content hashes stay reviewer-authored claims the receipts cannot
corroborate; a journal-blocked context has no operator-facing unblock command; and
no Windows-native or Codex-native session write restriction has been demonstrated,
so those adapters report a named blocker and publish nothing rather than claiming
support.

## Comments

- 2026-10-09 — Specification and authoritative procedure supplemented. Runtime
  isolation/report/publication mechanisms are not implemented by this document.
- 2026-10-09 — Development plan saved with exact file ownership, interfaces,
  regression assertions and verification commands. Runtime acceptance remains
  pending; planning performs no implementation or model session.
- 2026-10-10 — Implemented on `harden-011` by sub-agent-driven development: four
  tasks, each independently reviewed with mutation testing, two fix rounds on
  Task 3 and Task 4, and a whole-branch dogfood that walked the documented
  reviewer flow on the real WSL bubblewrap boundary and attacked the publication
  door. Acceptance evidence and the limits left in place are recorded in
  §"Verification record"; the suite of record is 488 tests, `OK (skipped=4)`.
- 2026-10-10 — HARDEN-009 stays blocked and is not satisfied by this Ticket: it
  needs genuinely supported adapters and newly authorized session budget, and no
  pilot evidence for it is inferred from these automated and single-host results.
