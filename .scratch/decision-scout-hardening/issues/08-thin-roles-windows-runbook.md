# 08: Thin role entries and Windows launch diagnostics

Ticket ID: HARDEN-008
Type: task
Status: implemented — integration evidence recorded 2026-10-09
Blocked by: None
Parent: [supplemental spec](../spec.md#c0--compatibility-and-authority)
Source findings: ST-02; O3: Windows launch; [disposition](../review-disposition.md)
Plan: [development plan](../../../docs/superpowers/plans/2026-10-08-harden-08.md)

## What to build

Each Harness follows one authoritative rule set, and a Windows policy failure has a bounded documented diagnostic path.

## Scope and ownership

Own the complete C0, C8 outcome from contract/documentation through public-command behavior and its regression or manual evidence. Exact files and interfaces are frozen in the linked plan. Honor its write set; other work may share mutation/validation files, so do not revert unrelated changes and schedule one writer for overlapping files. This issue is pending implementation; original SCOUT tickets stay historical.

## Acceptance criteria

- [x] Role Skills retain triggers/links/minimal commands while removing copied business contracts, quotas and gate/task rules.
- [x] All eight installed Skills and adapters point to authoritative Protocol/role/migration sections; installation remains idempotent.
- [x] Windows guidance cites the observed pilot rejection/fix, records read-only intent and distinguishes policy rejection from technical review.
- [x] Diagnostic version/help checks require no new model session; any live smoke needs available budget at execution.
- [x] No global model preference, local machine path, automatic policy-bypass retry or permission weakening is introduced.
- [x] Existing skill/install tests pass, and a manual rule-source audit records where each role obtains semantic requirements.

## Verification

Use the linked plan's named cases and commands. Negative mutations preserve State bytes; read-only operations preserve artifacts and Git index. HARDEN-009 has manual live acceptance and is not completed by automated fixtures. Global compatibility constraints in the supplemental spec apply to every slice.

## Escalation conditions

If implementation requires changing v2 digest semantics, completed task history, acceptance boundaries or dependencies beyond the linked contract, record the conflict before proceeding. Do not silently widen the slice or infer model-session budget from this planning request.

## Comments

- 2026-10-08 — Created from the post-implementation review at the user's request; ready for development planning/execution, not a resolved finding.
- 2026-10-09 — Implemented by 3cef3db; independently reviewed. Integration evidence: full-suite run at 3cef3db — `SkillsLintTest` (test_skills.py) and `InitTest` (test_init.py) passed, covering eight installed Skills, idempotent installation and user-AGENTS byte preservation; the manual rule-source audit is recorded at `.scratch/decision-scout-hardening/role-rule-source-audit.md` and the Windows runbook at `adapters/codex/windows.md` (launch/policy rejection distinguished from technical review; no new model session for version/help diagnostics).
