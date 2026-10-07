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

## v2 atomic escalation (workflow_version: 2)

On a `workflow_version: 2` Ticket, `ai-workflow escalate` is atomic and changes
the actual next action; a bare block edit is not enough. Version 1 Tickets keep
the loose behavior above unchanged.

### Setting

`ai-workflow escalate <ticket-id> --scope <machine|human> --reason "..."` writes
in one save:

- `escalation.previous_status` — the Status in effect when escalation began;
- `escalation.interrupted_action` — the `next_action` (`role`/`action`/`task`)
  that escalation interrupted;
- `escalation.interrupted_phase` — the phase when escalation began;
- `escalation.required: true`, `scope` and `reason`;
- `status: escalation_required`;
- `next_action` routed to the phase's senior resolver.

The resolver is chosen by phase:

| phase | resolver role |
|---|---|
| requirement | workflow-bootstrap |
| evidence_collection, evidence_audit, followup_evidence | evidence-auditor |
| technical_decision, planning, implementation, review | technical-decision |

Escalating a `done` or `abandoned` Ticket is rejected (nothing to interrupt).
Repeating an escalation updates `scope`/`reason` but keeps the stored
`previous_status`/`interrupted_action`/`interrupted_phase` (recorded on the first
escalation only). While escalated, `advance`, `complete-task`, and any
`set-status` other than `escalation_required` are rejected and change no State
bytes.

### Clearing

`ai-workflow escalate <ticket-id> --clear --resolution "<text>"` requires a
non-empty `--resolution` that describes the senior resolution **and** carries a
supporting reference: a document id (`F-<n>`/`DQ-<n>`), a repository-relative
path with a dotted extension (e.g. `decision.md`, `.ai/work/.../handoff.md`), or
a commit hash. A `human`-scope resolution must additionally reference the user's
answer; a human escalation is never resolved automatically.

Clearing records the text in `escalation.resolution` (kept afterwards), sets
`required: false`, keeps `scope` and the `interrupted_*` fields, clears `reason`,
restores `status` to the recorded `previous_status` (falling back to `active`
when it is not a valid Status), and recomputes `next_action` for the current
phase — a checked continuation, not an arbitrary phase reset. A previous status
of `escalation_required` is rejected as inconsistent. `validate` reports
escalation/Status/route divergence as ERROR findings.
