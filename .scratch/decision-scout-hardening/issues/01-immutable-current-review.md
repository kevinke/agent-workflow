# 01: Immutable and current Review bindings

Ticket ID: HARDEN-001
Type: task
Status: implemented — integration evidence recorded 2026-10-09
Blocked by: None
Parent: [supplemental spec](../spec.md#c1--immutable-current-review-identity-harden-001)
Source findings: S-01, S-09, ST-01; [disposition](../review-disposition.md)
Plan: [development plan](../../../docs/superpowers/plans/2026-10-08-harden-01.md)

## What to build

A receiver and completion gate agree on the exact immutable change reviewed, for both pass and changes_requested.

## Scope and ownership

Own the complete C1 outcome from contract/documentation through public-command behavior and its regression or manual evidence. Exact files and interfaces are frozen in the linked plan. Honor its write set; other work may share mutation/validation files, so do not revert unrelated changes and schedule one writer for overlapping files. This issue is pending implementation; original SCOUT tickets stay historical.

## Acceptance criteria

- [x] Literal full/short object IDs resolve once to a full commit OID; HEAD/branch/tag names reject without State writes.
- [x] Legacy symbolic bindings are surfaced as stale and require new review; no automatic authentication by resolving current HEAD.
- [x] Changed Review bytes, relevant code/history and Plan block validate, resume and mutations for both recorded verdicts.
- [x] Valid pending and appended changes_requested rework remain usable; completed task contracts stay unchanged.
- [x] Current pass still permits workflow-only commits and done; v1 behavior is preserved.

## Verification

Use the linked plan's named cases and commands. Negative mutations preserve State bytes; read-only operations preserve artifacts and Git index. HARDEN-009 has manual live acceptance and is not completed by automated fixtures. Global compatibility constraints in the supplemental spec apply to every slice.

## Escalation conditions

If implementation requires changing v2 digest semantics, completed task history, acceptance boundaries or dependencies beyond the linked contract, record the conflict before proceeding. Do not silently widen the slice or infer model-session budget from this planning request.

## Comments

- 2026-10-08 — Created from the post-implementation review at the user's request; ready for development planning/execution, not a resolved finding.
- 2026-10-09 — Implemented by 0f1f2b5 and 477e65c; independently reviewed. Integration evidence: full-suite run at 3cef3db (399 tests; the single failure belongs to HARDEN-002's fixture) — `ReviewV2Test.test_review_rejects_symbolic_refs`, `test_review_short_oid_is_canonicalized`, `test_symbolic_stored_binding_is_stale`, `test_changed_failed_review_blocks_validate_resume_repair`, `test_failed_review_append_keeps_prefix` and `test_hex_named_ref_does_not_override_object_identity` all passed; the installed-kit followup/append/repair/re-review/done path is covered by `InstalledLifecycleV2Test.test_installed_lifecycle_with_followup_and_rework` (passed), so v1/pending behavior stays intact.
