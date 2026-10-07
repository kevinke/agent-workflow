# Plan — <ticket-id>

The Plan is the registered execution contract (see `.ai/workflow/ARTIFACTS.md`).
It is a referenced source artifact, integrated by reference and never copied into
`.ai/`. On a `workflow_version: 2` Ticket the executor registers it:

```
ai-workflow register-plan <ticket-id> --path <this file> --total <N>
```

Registration stores the path, the Plan's byte hash, and one canonical hash per
ordered task; it does not count any task complete.

## Metadata

```yaml
artifact_type: plan
format_version: 1
ticket_id: <ticket-id>
task_count: <number of ordered Task sections below>
```

## Task 1

### Objective
<one bounded step an executor can complete without inventing design>

### Inputs
<referenced Fact IDs and the decision from decision.md>

### Allowed changes
<the files or areas the executor may modify>

### Protected scope
<behavior, interfaces, or data that must not change>

### Invariants
<properties that must still hold before and after the step>

### Acceptance criteria
<observable conditions that make the task complete>

### Verification
<exact commands and the expected outcomes>

### Dependencies
N/A | <earlier task numbers, e.g. Task 1; forward or self references are invalid>

### Escalation conditions
<what forces a senior decision instead of executor improvisation>

Add `## Task 2`, `## Task 3`, … in order. Dependency numbers may only reference
earlier tasks; a justified `N/A` is valid, a bare empty placeholder is not.