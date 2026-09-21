# Escalation

## Two scopes

Every escalation has exactly one scope:

- `machine` (default) — resolved by a senior role. Applies to evidence shortage, decision conflict, and plan deviation. A machine escalation never interrupts the user.
- `human` — escalates to the user. This is the only scope that interrupts the user.

## Recording

Set the `escalation` block in `state.yaml`:

```yaml
escalation:
  required: true
  scope: machine   # or: human
  reason: <what is blocking and why>
```

While escalated, `next_action.role` locks to a senior role; the senior resolves the underlying issue.

## Resolution

1. A senior role takes `next_action`.
2. The senior resolves the underlying issue (collects missing evidence, adjudicates the decision conflict, or realigns the plan).
3. The senior clears the escalation block (`required: false`, keep scope, clear reason) and records the resolution in handoff.md.
4. The normal phase flow resumes.
