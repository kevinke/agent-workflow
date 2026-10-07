# Review disposition — 2026-10-08

Status: ready-for-agent
Source: [full review with reproductions](../decision-scout-port/post-implementation-review-2026-10-08.md)
Baseline reviewed: `5ae8e27..00a3904`; follow-up implementation has not started.
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

## Evidence status and delivery priority

The original live bug/feature review paths are historical successes. The later
review's full unittest run had one dirty-edit failure; an isolated rerun passed.
That is unresolved evidence for HARDEN-002, not an all-green baseline. Seven of
eight bound archive identities differ in committed text blobs even though the
verified working bytes match. Keep both findings visible until their owners
supply deterministic regression and fresh-clone evidence respectively.

Start with HARDEN-001/002, then recovery and preservation. The index lists actual
blocking edges separately from suggested priority and shared-file scheduling.
Do not reopen or rewrite old pilot results to manufacture a new completion.

## Comments

- 2026-10-08 — User requested spec supplementation, separate tickets and development plans; all are prepared as documentation, with runtime work pending.
