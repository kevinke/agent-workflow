# Review disposition — 2026-10-08

Status: original automated findings verified; S-10/O4 open; O5 verified locally/pending commit; HARDEN-009 awaits 10/11 and live budget
Source: [full review with reproductions](../decision-scout-port/post-implementation-review-2026-10-08.md)
Baseline reviewed: `5ae8e27..00a3904`; the follow-up fixes have since landed on branch `decision-scout-hardening` (see Evidence status below).
Spec: [supplemental contracts](spec.md)
Delivery: [tickets](tickets.md) · [plans](../../docs/superpowers/plans/2026-10-08-scout-hardening.md)

“Existing bug” means the original spec already promises the behavior. A spec
clarification makes the implementation boundary precise; it does not downgrade
that bug. “New contract” extends the old machine-enforced boundary. Every row has
one owning ticket; combined findings share a verifiable outcome.

| Review item | Disposition | Spec contract | Owning ticket | Reason / acceptance evidence |
|---|---|---|---|---|
| S-01 + ST-01: moving Review commit | Existing bug; freeze accepted ID forms | C1 | HARDEN-001 | Only immutable OIDs; changed HEAD cannot retarget recorded pass; old symbolic bindings stale. |
| S-02: copied index hides dirty code | Existing bug; no new product contract | C2 | HARDEN-002 | Equal-size, equal-timestamp dirty edit detected without modifying original index. |
| S-03: escalation/bootstrap deadlock | Existing bug; recovery contexts clarified | C3 | HARDEN-003 | Audit/register/clear roundtrip works for ordinary, upgrade and bootstrap recovery. |
| S-04: clear restores incoherent executor | Existing bug; atomic restore clarified | C3 | HARDEN-003 | Missing/stale retained-phase contracts reject clear with unchanged State. |
| S-05: Git archive loses raw hashes | Existing portability defect; new export contract | C6 | HARDEN-006 | Fresh clone/export retains all original bound bytes; no historical re-gate. |
| S-06: malformed Evidence accepted | Existing traceability bug; grammar/types clarified | C5 | HARDEN-005 | Code line AND symbol, valid source families, references and typed metadata required. |
| S-07: upgrade deletes unknown nested keys | Existing explicit preservation bug | C4 | HARDEN-004 | All extension fields survive, including under upgrade. |
| S-08: scalar map input crashes conversion | Existing safe-rejection bug; preflight clarified | C4 | HARDEN-004 | Parseable malformed maps reject without traceback or bytes changed. |
| S-09: stale failed Review validates | Existing command/validate disagreement | C1 | HARDEN-001 | Both verdicts checked; valid appended-rework exception retained. |
| ST-02: Skill-local semantic copies | Existing ADR/rule-source violation | C0, C8 | HARDEN-008 | Thin entry points refer to Protocol; no copied gate/task/field definitions. |
| ST-03: duplicated artifact/phase checks | Design judgment; targeted extraction | C3 | HARDEN-003 | Shared retained-phase checks serve recovery and validation; no standalone broad refactor. |
| O1: Scout and decision share reported model | Measurement gap; supplemental experiment | C9 | HARDEN-009 | Distinct actual decision model and cross-Harness receiving context demonstrated. |
| O2: unfilled Handoff validates | New syntactic gate; acceptance stays independent | C7 | HARDEN-007 | Early drafts allowed; unchanged placeholders rejected at transfer boundaries. |
| O3: Windows launch setup | Operational follow-up; host-specific guidance | C8 | HARDEN-008 | Diagnosis and limits captured in thin adapter docs; no global permission changes. |
| S-10: index flags hide dirty tracked files | Existing currentness defect; C2 follow-up | C2 index flags | HARDEN-010 | Public set-review reproduction admits changed source with assume-unchanged; both flags need byte-preserving regressions. |
| O4: reviewer can write live tests/fixtures temporarily | New enforced isolation/publication contract | C10 | HARDEN-011 | External incident is unattributed; snapshot + actual denied-live-write boundary + identity-checked publication required. |
| O5: protection template CRLF breaks byte assertions | Local checkout/installation defect | C11 | HARDEN-012 | Narrow LF attribute rule and template restoration verified locally: 17 focused tests, six clone/install cases and 400 integration tests; commit pending. |

## Decisions that constrain implementation

1. Preserve v2 raw-byte SHA-256. Protect transport and add verified export rather
   than changing what historical State digests mean. A canonical newline hash
   scheme is deferred to a separately versioned migration proposal.
2. Review accepts literal object IDs, resolves abbreviations once and records a
   full OID. Do not reinterpret historical HEAD/branch values as valid approvals.
3. Recovery is an explicit, bounded senior path. It does not authenticate the
   process's model or allow executor writes through unresolved escalation.
4. Shared phase checks are part of HARDEN-003. No architecture-only ticket or
   unrelated refactor is necessary to deliver the observed repair.
5. Structurally valid reports and completed handoffs still need technical review.
   Tighten syntax without treating it as proof of truth or acceptance.
6. Original SCOUT-008 remains complete. HARDEN-009 validates a different claim;
   its live run consumes a newly authorized available budget, not the old cap.

## Latest follow-up evidence (2026-10-09)

S-10 remains open: the public v2 fixture rejected changed src/feature.py, then
recorded pass after assume-unchanged was set; skip-worktree also hid drift.
Clearing flags was independently observed to change the copied index mtime,
so the repair must retain earlier racy-stat protection. O4 also remains open:
this repository cannot attribute the user's external temporary-test incident,
and a restored final tree is not proof of an enforced write boundary. The
Protocol/provenance requirements are now written; runtime enforcement is not.

O5 is verified locally, not published: root attributes pin only the installer
protection template, whose restored LF bytes match HEAD; 400 tests passed in
163.087s and all six actual clone/install cases passed. The fix did not change
other pre-existing tracked bytes or historical pilot packages. Details live in
Ticket 12. Original 01–08 completion below remains the historical run record.

## Original evidence status and delivery priority

Update 2026-10-09 — every fix-bearing finding now has a landed, independently
reviewed fix on `decision-scout-hardening`: S-01/ST-01/S-09 (HARDEN-001:
0f1f2b5, 477e65c), S-02 (HARDEN-002: 8a0b92b), S-03/S-04/ST-03 (HARDEN-003:
235bc88, 256b312, fba580a, bf9b016), S-07/S-08 (HARDEN-004: d822833, b76f51f),
S-06 (HARDEN-005: 46d50c0), S-05 (HARDEN-006: 793ac20, 3014423, 9ee8a4f,
cebc72), O2 (HARDEN-007: 924a580) and ST-02/O3 (HARDEN-008: 3cef3db). The
2026-10-09 one-shot integration run
(`PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s scripts/ai-workflow/tests -p 'test_*.py' -v`
at 3cef3db: 399 tests, 397 passed, 2 pre-existing symlink-privilege skips,
1 failure) passed every slice's named regression except HARDEN-002's
`test_racy_edit_blocks_done_and_resume`, which failed in test-fixture setup
before exercising production code: on this Windows host the following `git add`
process observed the file's pre-backdate mtime, so the fixture's determinism
precondition fired. It is diagnosed as a host cross-process mtime-visibility
race, not a recurrence of the S-02 dirty-edit escape: the same helper passed
four other times in that run, the deterministic detection regressions
(`test_racy_equal_size_edit_is_detected_read_only`,
`test_racy_drift_with_real_index_lock`) passed, and the installed-kit lifecycle
(`InstalledLifecycleV2Test.test_installed_lifecycle_with_followup_and_rework`)
and v1 compatibility cases passed. A same-day run of record at 483a423 (racy
fixture hardening in `test_review_v2.py` only; scoped re-review passed) finished
`Ran 399 tests in 372.617s` — `OK (skipped=2)`, exit 0, including
`test_racy_edit_blocks_done_and_resume`, so S-02's caveat is closed and every
automated slice's named regression has passed in a full-suite run. The earlier baseline
observations (one dirty-edit failure with a passing isolated rerun; seven of
eight archive identities differing in committed text blobs) are resolved by
8a0b92b and the verified fresh-clone export evidence in
`.scratch/decision-scout-port/pilot/archive-manifest.md` (9ee8a4f).
O1 (HARDEN-009) remains open: no live run has occurred, and it consumes a newly
authorized session budget.

## Comments

- 2026-10-08 — User requested spec supplementation, separate tickets and development plans; all are prepared as documentation, with runtime work pending.
- 2026-10-09 — Evidence updated after integration: landed fixes are listed per finding in Evidence status with the slices' named-test evidence from the single full-suite run. S-02 keeps one open caveat (racy done/resume fixture awaiting a rerun-of-record). O1/HARDEN-009 stays pending — no live sessions were run and no budget was authorized; historical pilot results remain unchanged.
- 2026-10-09 — Caveat closed by the green run of record at 483a423: after the racy fixture hardening (`test_review_v2.py` only, scoped re-review passed), the full suite finished `OK (skipped=2)` with exit 0 including the racy done/resume regression. All fix-bearing findings S-01..S-09, ST-01..ST-03 and O2/O3 now have landed fixes plus full-suite evidence; O1/HARDEN-009 remains open — still no live run and no authorized session budget.

- 2026-10-09 — Added S-10/O4/O5 disposition and Tickets 10–12. 10/11 have
  specifications but no implemented fix; 12 is verified locally/pending commit.
  HARDEN-009 launch now consumes 10/11 while retaining its separate budget gate.
