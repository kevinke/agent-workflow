# Review — <ticket-id>

The Reviewer's verdict on the current change and Plan (see
`.ai/workflow/ARTIFACTS.md`). A scaffold is not a verdict: `set-review` rejects
this file until the Metadata is filled in and the four sections carry real
content (structural validity is not proof that acceptance criteria passed).

## Metadata

```yaml
artifact_type: review
format_version: 1
ticket_id: <ticket-id>
reviewed_commit: <commit hash reviewed by this Review>
plan_sha256: <SHA-256 of the registered Plan>
verdict: <pass | changes_requested>
```

## Acceptance results

<the observable acceptance-criterion outcomes for the reviewed change>

## Verification results

<the commands run and their observed results — never infer a pass from tests alone>

## Findings

<the review findings, or the explicit None for a passing review>

## Required rework

<the appended rework tasks needed, or the explicit None for a passing review>