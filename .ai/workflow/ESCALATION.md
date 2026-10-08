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

### Senior recovery while escalated (workflow_version 2)

An unresolved escalation is a bounded recovery context. While it is active, the
senior resolver may re-audit Evidence (`set-gate`) and register a corrected
Plan (`register-plan`) outside their ordinary phases — the same allowance a
recorded v1→v2 reconstruction has. Routine execution and forward transitions
stay blocked, and the allowance is re-derived from the live State on every
command: after the escalation clears, out-of-phase writes are rejected again.
This is a workflow condition, not model authentication.

### Clearing

`ai-workflow escalate <ticket-id> --clear --resolution "<text>"` requires a
non-empty `--resolution` that describes the senior resolution **and** carries a
supporting reference: a document id (`F-<n>`/`DQ-<n>`), a repository-relative
path with a dotted extension (e.g. `decision.md`, `.ai/work/.../handoff.md`), or
a commit hash. A `human`-scope resolution must additionally reference the user's
answer; a human escalation is never resolved automatically.

The clear is atomic and checked. It prepares the proposed cleared State (a deep
copy: recovery/escalation flags provisionally cleared, the recorded previous
Status restored, `next_action` recomputed for the retained phase) and judges it
against the retained phase's current contracts before anything is saved —
required artifacts, a current sufficient gate for a decisionward phase, the
structured artifact contracts, a current registered Plan with coherent counters
and a confirmed adoption checkpoint in an execution phase, and any recorded
Review verdict's immutable bindings. A pending Review is clearable only with
every original task complete; a valid recorded `changes_requested` with its
strictly-appending rework Plan may clear into the normal repair path. A
rejected clear changes no State bytes and reports the unsatisfied contracts.

On success the single save records the resolution text in
`escalation.resolution` (kept afterwards), sets `required: false`, keeps
`scope` and the `interrupted_*` fields, clears `reason`, restores `status` to
the recorded `previous_status` (falling back to `active` when it is not a valid
Status; `escalation_required` is rejected as inconsistent), and recomputes
`next_action` for the retained phase — a checked continuation, not an arbitrary
phase reset. A `paused`/`blocked` previous Status is restored as-is: it is a
real interruption, not silently made executable. The cleared flags grant no
continuing out-of-phase write permission. `validate` reports
escalation/Status/route divergence as ERROR findings.
