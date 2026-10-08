# 07: Phase-aware Handoff readiness

Ticket ID: HARDEN-007
Type: task
Status: implemented — integration evidence recorded 2026-10-09
Blocked by: 03
Parent: [supplemental spec](../spec.md#c7--phase-aware-handoff-readiness-harden-007)
Source findings: O2: Handoff placeholders; [disposition](../review-disposition.md)
Plan: [development plan](../../../docs/superpowers/plans/2026-10-08-harden-07.md)

## What to build

A model taking over review or completion gets a concrete handoff while early workflow drafts remain usable.

## Scope and ownership

Own the complete C7 outcome from contract/documentation through public-command behavior and its regression or manual evidence. Exact files and interfaces are frozen in the linked plan. Honor its write set; other work may share mutation/validation files, so do not revert unrelated changes and schedule one writer for overlapping files. This issue is pending implementation; original SCOUT tickets stay historical.

## Acceptance criteria

- [x] Unchanged scaffold and whole-field/structured-bullet placeholders block review entry, review/done continuation, completion and late recovery clear.
- [x] All required Handoff sections and Repository State fields have concrete content at those boundaries.
- [x] Early-phase drafts remain accepted with notices; implementation recovery clear requires a concrete handoff.
- [x] Explicit None, justified N/A and useful angle-bracket code/literals pass; syntax checks do not claim acceptance proof.
- [x] CLI guards and validation/resume agree through the shared phase checks; fixture helpers generate concrete handoffs rather than disabling the gate.

## Verification

Use the linked plan's named cases and commands. Negative mutations preserve State bytes; read-only operations preserve artifacts and Git index. HARDEN-009 has manual live acceptance and is not completed by automated fixtures. Global compatibility constraints in the supplemental spec apply to every slice.

## Escalation conditions

If implementation requires changing v2 digest semantics, completed task history, acceptance boundaries or dependencies beyond the linked contract, record the conflict before proceeding. Do not silently widen the slice or infer model-session budget from this planning request.

## Comments

- 2026-10-08 — Created from the post-implementation review at the user's request; ready for development planning/execution, not a resolved finding.
- 2026-10-09 — Implemented by 924a580 (including out-of-set fixture repairs accepted by review); independently reviewed. Integration evidence: full-suite run at 3cef3db — `HandoffReadinessV2Test.test_scaffold_blocks_review_entry`, `test_early_handoff_draft_is_notice_only`, `test_handoff_nested_placeholders_rejected`, `test_handoff_concrete_empty_cases_and_literals` and `test_handoff_boundary_agreement` all passed; the passing review/escalation/lifecycle suites confirm CLI guards, validation and resume agree through the shared phase checks, with fixture helpers (`V2CLITestCase.write_handoff`) generating concrete handoffs.
