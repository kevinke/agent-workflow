# Artifact Contracts

All artifacts live under `.ai/work/<ticket-id>/`. Each has one writer role, an allowed content set, and a forbidden content set.

| Artifact | Writer | Content | Forbidden |
|---|---|---|---|
| evidence.md | scout | FACT / INFERENCE / UNKNOWN entries; important FACTs carry anchors | design proposals |
| evidence-audit.md | evidence-auditor | sufficiency answers only | recommendations, designs |
| decision.md | technical-decision (senior-only) | chosen approach, rejected alternatives, invariants, compatibility, API/schema decisions, risks, escalation boundaries | undecided design questions |
| progress.md | ticket-executor | task-granularity log: completed task, files changed, tests run, deviation, open issues | every shell command |
| handoff.md | checkpoint-handoff (or the departing agent) | fixed sections + Repository State block | unverified claims |

## evidence.md

Only entries tagged `FACT`, `INFERENCE`, or `UNKNOWN`. Important FACTs carry anchors: file path, symbol, line, command, or test result. Design proposals are forbidden. Adopted repos carry a Migration Notice (see MIGRATION.md).

## evidence-audit.md

Answers only four questions:

1. Is the evidence sufficient to enter technical_decision?
2. What is missing?
3. Why might the gap change a decision?
4. What should the next scout collect precisely?

## decision.md

Written only by a senior model (technical-decision role). Contains:

- Chosen approach
- Rejected alternatives
- Invariants
- Compatibility
- API / schema decisions
- Risks
- Escalation boundaries

Adopted repos add a Provenance section recording only the still-valid API/schema/invariants/architecture (see MIGRATION.md).

## progress.md

Execution log at task granularity: completed task, files changed, tests run, deviation from plan, open issues. Not every shell command.

## handoff.md

Fixed sections: What was done / What remains / Important discoveries / Current failure if any / Do not repeat / Next recommended action. Plus a Repository State block: branch, HEAD, uncommitted files, test status.
