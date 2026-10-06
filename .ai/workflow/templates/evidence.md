# Evidence — <ticket-id>

The Evidence artifact is the Scout Report (see `.ai/workflow/ARTIFACTS.md` for
the full contract). Design proposals and the evidence verdict are forbidden.

## Metadata

```yaml
artifact_type: evidence
format_version: 1
ticket_id: <ticket-id>
round: <positive current collection round; must match Audit/CLI round>
observed_commit: <repository HEAD at collection time>
dirty_changes: [<relevant working-tree paths, or []>]
created_at: <collection time>
scout_harness: <harness name>
scout_model: <model name>
# Optional descriptive fields, not State:
# task_type: bug | feature | ...
# report_status: partial | ready-for-audit
```

## Decision Questions

Three to eight is guidance, not a quota. If the ticket supplies no questions,
draft them from the request; escalate ambiguity requiring an architectural
choice. Use H3 `DQ-01` (two or more digits) with named fields.

### DQ-01

**Question:** <the question as investigated>

**Decision affected:** <which decision this question feeds>

**Evidence targets:** <likely files, areas, or behaviors worth collecting>

**Answer:** ANSWERED | UNKNOWN

**Facts:** <linked F-IDs, or an explicit UNKNOWN fact-link value>

## Findings

Use H3 `F-01 [FACT | INFERENCE | UNKNOWN]` with named fields. FACT means an
observed claim. Static reading, execution, and test verification are distinct —
do not present static reading as runtime verification. INFERENCE cites its
Basis (F-IDs); UNKNOWN states decision impact.

### F-01 [FACT]

**Statement:** <one precise claim>

**Questions:** <associated DQ IDs>

**Sources:**
- code: <repo-relative path>:<line-range> :: <symbol when one exists>
- runtime: <command> / <input or fixture> / <observed result> / <exit status>
- negative search: <scope searched> / <exclusions> / <nothing found>

**Method:** static | execution | test | inference | unknown

**Scope:** <limits of the claim>

## Unknowns

Name the unresolved DQ/F IDs, the decision impact, and the next collection
step; explicit `None` is valid. A critical UNKNOWN does not block report
readiness, but it cannot open the Evidence Gate — only the auditor judges
sufficiency.

## Handoff

- **Established Fact IDs:** <F-IDs the decision can rely on>
- **Decisions still required:** <open decision points>
- **Missing evidence:** <precise gaps, not "investigate more">
- **Already investigated:** <areas and negative searches>
- **Stopping reason:** <why further collection will not change a decision, or the budget/scope stop>

Prior rounds stay below with their own Metadata round value; preserve prior
DQ/F IDs and collection history when appending follow-up facts.
