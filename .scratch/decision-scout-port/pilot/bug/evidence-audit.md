# Evidence Audit - PILOT-BUG-01

Audits sufficiency only. No recommendations, no designs.

## Metadata

```yaml
artifact_type: evidence-audit
format_version: 1
ticket_id: PILOT-BUG-01
round: 1
gate: sufficient
evidence_sha256: 71855e12d011d2d7345577633af211ae15e801b7e2b7e7056d8385dd9ab3a3f2
```

## Is the evidence sufficient to enter technical_decision?

Yes. DQ-01, DQ-02 and DQ-03 are all ANSWERED and trace every claim to F-01
through F-04 with both static code sources (service.py:1-3, service.py:5-6) and
one execution source (python demo.py printing initial=1, configured=2,
actual=1, exit 0). F-03's inference is grounded in F-01 plus F-02 and states
its own scope limit. The negative search in F-04 is scoped and justified. The
observed_commit b5a13a883095 differs from HEAD 9563942ad7a5, but the diff
touches only .ai/work metadata and a removed __pycache__ artifact; service.py
and demo.py are byte-identical at both commits, so every code anchor and the
runtime observation remain relevant and are not discarded.

## What is missing?

- No decision-changing gap within the ticket scope. DQ-01/02/03 are answered.
  Traceability, verification limits (single run, one Python version) and
  unknowns (explicitly None) are all declared, and the only residual open item
  is the fix shape, which is a decision for technical_decision rather than a
  gap in evidence.

## Why might the gap change a decision?

- Not applicable. No missing evidence was identified, so no gap can change a
  decision. The fix-shape choice (live re-read versus snapshot plus reload
  versus documenting immutability) is fully bounded by F-01, F-03 and F-04;
  F-04 confirms demo.py is the only consumer, so the regression surface is
  known before the decision is taken.

## What should the next scout collect precisely?

- Not applicable. All in-scope questions are answered and no further
  repository behavior relevant to the defect remains to collect. No follow-up
  scout round is required.
