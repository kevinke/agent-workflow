# state.yaml Schema (schema_version 1)

`state.yaml` is the machine-readable authoritative per-ticket workflow state. Every harness reads it first.

## Versions

- `schema_version: 1`
- `workflow_version: 1`

### `workflow_version` (v2 extension)

`schema_version` stays fixed at 1. `workflow_version` selects the rule set and
is additive:

- `1` — the current fixed default. Existing Tickets and the template keep this
  value; an absent field means `1`, so every pre-existing State reads as v1.
- `2` — an explicit upgrade to the stricter v2 contracts.

Only the integers `1` and `2` are accepted. A boolean (`true`/`false`), zero,
a string such as `"2"`, or any future value such as `3` is rejected: `validate`
reports it as an ERROR Finding and a mutation refuses it before writing State,
without a traceback and without changing the State bytes. Version 1 Tickets
retain their exact semantics until explicitly upgraded; the template is not
bumped by this extension.

## Phases

`requirement`, `evidence_collection`, `evidence_audit`, `followup_evidence`, `technical_decision`, `planning`, `implementation`, `review`, `done`. `UNINITIALIZED` is the repo-level state before any ticket exists.

Allowed transitions:

```
requirement -> evidence_collection
evidence_collection -> evidence_audit
evidence_audit -> technical_decision      (requires evidence.gate = sufficient)
evidence_audit -> followup_evidence       (evidence.gate = insufficient)
followup_evidence -> evidence_audit
technical_decision -> planning
planning -> implementation
implementation -> review
review -> done
```

No other phase transitions exist. At `done`, `next_action` is cleared.

## Lateral statuses

`active`, `blocked`, `escalation_required`, `paused`, `abandoned`. A status is orthogonal to phase: `phase: implementation, status: blocked` is valid. Status is never merged into phase.

## Top-level blocks

| Field | Type | Meaning |
|---|---|---|
| schema_version | int | fixed at 1 |
| workflow_version | int | fixed at 1; bumped only by an explicit upgrade |
| ticket | map {id, title} | ticket identity |
| phase | scalar | one of the phases above |
| status | scalar | one of the lateral statuses above |
| repository | map {base_commit, branch} | git anchor |
| source_artifacts | map {spec: {path}, ticket: {path}, plan: {path}} | references only, never copies |
| artifacts | map {evidence, evidence_audit, decision, progress, handoff} | artifact filenames |
| evidence | map {round, gate} | gate: sufficient / insufficient |
| implementation | map {current_task, total_tasks, completed_tasks: []} | task progress |
| escalation | map {required, scope, reason} | scope: machine / human |
| claim | map {harness, model, claimed_at} | soft claim, advisory |
| next_action | map {role, action, task} | intended next step |
| provenance | map {last_harness, last_model} | who wrote last |
| updated_at | scalar (ISO-8601) | stamped on every save |

## Restricted YAML subset (ADR-0002)

`state.yaml` is parsed by a hand-written parser supporting only the constructs the fixed schema uses:

- Block-style nested maps
- Block-style sequences (dash items); an empty sequence is written `[]`
- Scalars: quoted or plain strings, integers, booleans, `null`
- `null` for absent values

Rejected (validate must error): YAML anchors and aliases (`&`, `*`), tags (`!`), flow-style collections, multi-line block scalars (`|`, `>`), multi-document streams (`---`, `...`), and any construct outside the subset.

## Unknown fields

Unknown fields are silently ignored — never an error, never deleted. A harness editing `state.yaml` must preserve unknown fields it does not understand.

## Updating

Every save stamps `updated_at` with the current ISO-8601 timestamp.

## v2 Ticket structural validation

`validate` reads `workflow_version` first. Version 1 Tickets keep their existing
validation unchanged. A Version 2 Ticket is additionally checked against the
artifact grammar in `ARTIFACTS.md`:

- In `requirement` and `evidence_collection`, an Evidence report may still be a
  pending scaffold. Shape problems there are WARN, and a scaffold is never
  treated as a completed report (its placeholders are not structural failures).
- From `evidence_audit` onward, a present `evidence.md` must be a structurally
  valid report: a grammar violation or any structural problem is an ERROR.
- From `technical_decision` onward, a present `evidence-audit.md` must be
  structurally valid, and its Metadata `round` and `gate` must match the State
  and CLI values.

Structural validity is not proof that acceptance criteria passed; it checks
required sections, IDs, references, tags, metadata and anchor presence only.
This extension adds only version selection and structural validation; the
remaining additive v2 State fields are introduced by later Tickets.

## Migration blocks (adopted repos only)

Adopted repos (`ai-workflow adopt`, spec §10) may carry three additional top-level
blocks. They are **optional and adoption-only**: the fixed template and every
greenfield `start` ticket omit them. They are within the same restricted YAML
subset but, like all optional fields, are currently **not enforced by
`validate`**. The unknown-fields rule above still applies to any field not listed
here.

### `migration`

Records that this ticket came from an existing repo and at which phase.

```yaml
migration:
  adopted_existing_repo: true
  adopted_at_phase: implementation
```

### `historical_phases`

For each phase (`requirement` … `done`), how the phase is known to have occurred
prior to adoption. Values: `confirmed` (evidence-anchored), `inferred`,
`existing` (artifact present, unverified), `not_performed` (never executed).
`adopt` scaffolds every phase as `not_performed`; a senior marks the true value
with anchors during phase reconstruction (see `MIGRATION.md`).

```yaml
historical_phases:
  requirement: {status: inferred}
  evidence_collection: {status: not_performed}
```

### `adoption_checkpoint`

Gates whether the ticket may be handed to a cheap executor. All six fields stay
`false` until a senior confirms them; `continuation_safe: true` is required
before any `ticket-executor` may proceed (see `MIGRATION.md`).

```yaml
adoption_checkpoint:
  repository_understood: true
  active_ticket_identified: true
  current_phase_identified: true
  remaining_work_identified: true
  critical_invariants_identified: true
  continuation_safe: true
```

The `next_action.role` on an adopted-but-unconfirmed ticket is `workflow-bootstrap`,
never `ticket-executor`, so a cheap executor cannot read an execution instruction
until `continuation_safe: true`.
