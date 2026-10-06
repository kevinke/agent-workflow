# Evidence Audit — <ticket-id>

Audits sufficiency only. No recommendations, no designs. The verdict is
recorded separately with `ai-workflow set-gate` and binds to the Evidence
SHA-256 computed at that time (see `.ai/workflow/ARTIFACTS.md` for the full
contract).

## Metadata

```yaml
artifact_type: evidence-audit
format_version: 1
ticket_id: <ticket-id>
round: <round audited; must match the Evidence report round>
gate: <sufficient | insufficient>
evidence_sha256: <SHA-256 of the audited evidence.md, computed at set-gate>
```

## Is the evidence sufficient to enter technical_decision?

<yes / no — assess DQ coverage, traceability, verification limits, and
decision-changing unknowns within this answer>

## What is missing?

- <gap, tied to DQ/F IDs>

## Why might the gap change a decision?

- <impact, or a justified not-applicable>

## What should the next scout collect precisely?

- <instruction precise enough to act on, or a justified not-applicable>
