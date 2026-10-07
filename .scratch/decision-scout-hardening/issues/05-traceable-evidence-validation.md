# 05: Concrete and traceable Evidence validation

Ticket ID: HARDEN-005
Type: task
Status: ready-for-agent
Blocked by: None
Parent: [supplemental spec](../spec.md#c5--traceable-structural-evidence-harden-005)
Source findings: S-06; [disposition](../review-disposition.md)
Plan: [development plan](../../../docs/superpowers/plans/2026-10-08-harden-05.md)

## What to build

A cheap Scout report accepted by the gate has concrete metadata, usable locators and valid question/fact references.

## Scope and ownership

Own the complete C5 outcome from contract/documentation through public-command behavior and its regression or manual evidence. Exact files and interfaces are frozen in the linked plan. Honor its write set; other work may share mutation/validation files, so do not revert unrelated changes and schedule one writer for overlapping files. This issue is pending implementation; original SCOUT tickets stay historical.

## Acceptance criteria

- [ ] Code Sources require positive ordered lines and a named anchor or justified file-scope; line-only/symbol-only reject.
- [ ] Supported runtime, configuration/data, inference, scoped negative-search and UNKNOWN examples pass; unrecognized source claims reject.
- [ ] ANSWERED Facts, finding Questions and INFERENCE Basis require existing stable IDs; explicit justified UNKNOWN remains valid.
- [ ] Observed commit, timestamps and provenance are concrete; Evidence/Audit rounds are positive typed integers matching each other and CLI.
- [ ] All six accepted-malformed review examples now reject set-gate without State changes, while existing valid examples retain useful semantics.
- [ ] Protocol, template and examples explain syntax limits and retain semantic sufficiency for senior audit.

## Verification

Use the linked plan's named cases and commands. Negative mutations preserve State bytes; read-only operations preserve artifacts and Git index. HARDEN-009 has manual live acceptance and is not completed by automated fixtures. Global compatibility constraints in the supplemental spec apply to every slice.

## Escalation conditions

If implementation requires changing v2 digest semantics, completed task history, acceptance boundaries or dependencies beyond the linked contract, record the conflict before proceeding. Do not silently widen the slice or infer model-session budget from this planning request.

## Comments

- 2026-10-08 — Created from the post-implementation review at the user's request; ready for development planning/execution, not a resolved finding.
