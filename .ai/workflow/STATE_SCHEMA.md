# state.yaml Schema (schema_version 1)

`state.yaml` is the machine-readable authoritative per-ticket workflow state. Every harness reads it first.

## Versions

- `schema_version: 1`
- `workflow_version: 1`

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
