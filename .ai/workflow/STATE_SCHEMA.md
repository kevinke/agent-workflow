# state.yaml Schema (schema_version 1)

`state.yaml` is the machine-readable authoritative per-ticket workflow state. Every harness reads it first.

## Versions

- `schema_version: 1` (fixed)
- `workflow_version: 1` or `2`

### `workflow_version`

`schema_version` stays fixed at 1. `workflow_version` selects the rule set and
is additive:

- `2` — the shipped default. `init` installs a v2 template, so every greenfield
  `start` ticket and every `adopt` on a current install begins on the stricter v2
  contracts.
- `1` — the frozen v1 semantics, retained for existing work. An existing v1
  Ticket keeps this value, an unupgraded v1 install (whose
  `.ai/workflow/templates/state.yaml` still reads `workflow_version: 1`) keeps
  producing v1 Tickets, and an absent field means `1`, so every pre-existing
  State reads as v1.

Only the integers `1` and `2` are accepted. A boolean (`true`/`false`), zero,
a string such as `"2"`, or any future value such as `3` is rejected: `validate`
reports it as an ERROR Finding and a mutation refuses it before writing State,
without a traceback and without changing the State bytes. A Ticket's version is
never promoted in place: `ai-workflow upgrade` upgrades only the installed
protocol and never rewrites a Ticket's `state.yaml`; converting an existing v1
Ticket is the explicit `upgrade-ticket` command (see `MIGRATION.md`).

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
review -> done                              (workflow_version 2: requires a current `pass`)
review -> implementation                    (workflow_version 2 only: append-only rework)
```

No other phase transitions exist. The `review -> implementation` edge is v2-only
(the append-only repair after a `changes_requested` Review). At `done`,
`next_action` is cleared and no transition leaves it.

## Lateral statuses

`active`, `blocked`, `escalation_required`, `paused`, `abandoned`. A status is orthogonal to phase: `phase: implementation, status: blocked` is valid. Status is never merged into phase.

## Top-level blocks

| Field | Type | Meaning |
|---|---|---|
| schema_version | int | fixed at 1 |
| workflow_version | int | 1 or 2; new work defaults to 2, an existing v1 Ticket reaches 2 only through `upgrade-ticket` |
| ticket | map {id, title} | ticket identity |
| phase | scalar | one of the phases above |
| status | scalar | one of the lateral statuses above |
| repository | map {base_commit, branch} | git anchor |
| source_artifacts | map {spec: {path}, ticket: {path}, plan: {path[, sha256]}} | references only, never copies; on v2 the registered plan also records its raw-byte sha256 |
| artifacts | map {evidence, evidence_audit, decision, progress, handoff[, review]} | artifact filenames; on v2 `artifacts.review` defaults to `review.md` |
| evidence | map {round, gate[, report_sha256, audit_sha256]} | gate: sufficient / insufficient; the two hashes bind a v2 verdict to the audited bytes |
| implementation | map {current_task, total_tasks, completed_tasks: [], [, task_hashes: []]} | task progress; on v2 task_hashes is the ordered canonical hash of each registered task |
| review | map {verdict, artifact_sha256, reviewed_commit, plan_sha256} | additive v2 Review binding; verdict: pending / pass / changes_requested |
| escalation | map {required, scope, reason[, previous_status, interrupted_action, interrupted_phase, resolution]} | scope: machine / human; the four bracketed fields are additive v2 escalation facts |
| upgrade | map {from_version, previous_gate, requires_reconstruction} | additive v2 conversion facts written by `upgrade-ticket`; absent on v1 |
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

## v2 Evidence Gate binding

Recording a verdict with `set-gate` on a `workflow_version: 2` Ticket binds it to
the audited bytes. The command validates the concrete reports and only then
writes `evidence.round`, `evidence.gate`, `evidence.report_sha256` (SHA-256 of
`evidence.md`) and `evidence.audit_sha256` (SHA-256 of `evidence-audit.md`):

- It is allowed only in `evidence_audit`, or while a bounded senior recovery
  context is active on a v2 Ticket: an ordinary unresolved escalation, a
  recorded v1→v2 reconstruction (`upgrade.requires_reconstruction`), or a
  late-phase bootstrap. The allowance is re-derived from the live State on
  every command and ends when the recovery clears; otherwise it is rejected.
- The Evidence must be a structurally valid report whose Metadata `round` is a
  positive integer, and the CLI/`--round` value must name that same round.
- The Audit must be structurally valid and its Metadata `gate`, `round` and
  `evidence_sha256` must agree with the command and the current Evidence bytes.

Once a sufficient verdict is bound, `advance` into a decisionward target
(`technical_decision` onward) and `validate` both reject a gate whose recorded
hashes no longer match the current `evidence.md` / `evidence-audit.md` (a stale
binding). Re-auditing and re-running `set-gate` clears it. An insufficient verdict
is expected to be superseded by the next follow-up round, so its aging binding is
not treated as a blocker. Rejections change no State bytes and report the stale
binding or the malformed report field. Version 1 Tickets keep the loose, unbound
`evidence` block; `report_sha256`/`audit_sha256` are written only on v2. The
remaining additive v2 State fields are introduced by later Tickets.

## v2 Plan registration

`register-plan <ticket-id> --path <plan> --total N` registers the referenced
execution Plan on a `workflow_version: 2` Ticket. It reads and structurally
validates the Plan (see `ARTIFACTS.md`), bounds the path to the repository
(rejecting nonexistent, absolute, outside-root, and symlink-escaping paths),
and checks the declared `--total` against the actual task count. It then writes:

- `source_artifacts.plan.path` — the repository-relative path, as given
- `source_artifacts.plan.sha256` — the SHA-256 of the Plan's raw bytes
- `implementation.total_tasks` — the task count
- `implementation.task_hashes` — the ordered canonical hash of each task

It does **not** count any task complete: `current_task` stays the completed
count and `completed_tasks` is preserved. Re-registration keeps the completed
prefix and counter history and refuses a rewritten completed contract, a new
total below the completed count, or a non-appending changes_requested review.
The completed prefix binds once: when a recovered Ticket has completed tasks
but no recorded `task_hashes` (a reconstructed v1 history), the first recovery
registration records them, and every later registration must match the recorded
contracts — even while the recovery is still active. Registration is allowed
only in `planning`, while a bounded senior recovery context is active (an
ordinary unresolved escalation, a recorded reconstruction, or a late-phase
bootstrap), or in an appending `changes_requested` review. A v1 Ticket, or any
other phase, is rejected. Every rejection leaves the State bytes unchanged
with an actionable error.

## v2 escalation fields

On a `workflow_version: 2` Ticket, `escalate` writes four additive `escalation`
fields and changes the Status/route atomically (spec decision 5; see
`ESCALATION.md`). An unresolved escalation is a valid State condition, not a
malformed State:

- `escalation.previous_status` — the Status in effect when escalation began.
- `escalation.interrupted_action` — a map `{role, action, task}` holding the
  `next_action` that escalation interrupted.
- `escalation.interrupted_phase` — the phase when escalation began.
- `escalation.resolution` — the recorded senior resolution text; **kept** after
  a clear.

These are recorded on the first escalation only: repeating an escalation updates
`scope`/`reason` and keeps the original `previous_status`/`interrupted_action`/
`interrupted_phase`. While `escalation.required` is true the Status is locked to
`escalation_required` and `next_action.role` is the phase's senior resolver;
`advance`, `complete-task`, and a `set-status` away from `escalation_required`
are rejected without changing State bytes. The unresolved escalation is a
bounded recovery context: the senior resolver may re-audit Evidence
(`set-gate`) and register a corrected Plan (`register-plan`) outside their
ordinary phases while it is active. `escalate --clear` requires a documented
`--resolution`, then prepares the proposed cleared State (flags provisionally
cleared, the recorded `previous_status` restored, the phase-appropriate
`next_action` recomputed) and checks it against the retained phase's current
contracts — required artifacts, gate, Plan, counters, adoption checkpoint, and
any recorded Review verdict's bindings — before the single save. A pending
Review is clearable only with every original task complete; a valid recorded
`changes_requested` with its appending rework Plan clears into the normal
repair path. A rejected clear changes no State bytes; a restored
paused/blocked Status is not silently made executable; and the cleared flags
grant no continuing out-of-phase write permission. `validate` reports
escalation/Status/route divergence (and malformed additive fields) as ERROR
Findings. `required`, `scope`, and `reason` keep their v1 meanings; the four
fields above are written only on v2.

## v2 Review binding

`set-review <ticket-id> --verdict pass|changes_requested` records the Reviewer's
verdict on a `workflow_version: 2` Ticket. It is allowed only in `review`, with
no unresolved escalation, a current registered Plan and coherent counters, every
registered task complete, a structurally valid `review.md` whose Metadata
`verdict` matches the CLI and whose `plan_sha256` matches the registered Plan,
and no review-blocking code drift since the reviewed commit. The Metadata
`reviewed_commit` must be a literal hexadecimal Git object ID — the
repository's full object ID, or an unambiguous abbreviation of at least seven
hex digits — resolving to a commit that is an ancestor of HEAD. HEAD, branch
and tag names are rejected even when they resolve, and a ref named like a
hexadecimal prefix never takes precedence over the object with that prefix. On
success it writes (additive, v2-only):

- `review.verdict` — `pass` or `changes_requested` (`pending` is the scaffold
  default before a verdict is recorded).
- `review.artifact_sha256` — SHA-256 of the Review artifact's raw bytes.
- `review.reviewed_commit` — the full resolved literal commit ID, canonicalized
  once at `set-review` time for both verdicts.
- `review.plan_sha256` — the registered Plan's raw-byte SHA-256.
- `artifacts.review` — the Review filename (default `review.md`).

Code drift is the union of committed, staged, unstaged, and untracked paths
since the reviewed commit, read with Git subprocess argument lists and
NUL-delimited output. Changing any path other than this Ticket's exact
`state.yaml`, `progress.md`, `handoff.md`, and `review.md` (including the
registered Plan) rejects the command. Missing Git, a Reviewed commit that does
not resolve as a literal hexadecimal object ID, a non-commit or ambiguous
match, or an unrelated history (not an ancestor of HEAD) also reject it.
Every rejection leaves the State bytes unchanged; Version 1 Tickets keep their
existing semantics.

Both recorded verdicts stay under the same immutability contract after
recording: `validate`, `resume`, and the mutation guards re-check a recorded
`pass` and a recorded `changes_requested` against their Review artifact bytes,
their literal immutable commit, the registered Plan, and the reviewed code. A
previously stored symbolic `reviewed_commit` (for example `HEAD` or a branch
name from an older State) is stale: it is reported as an ERROR and requires a
new independent review — today's HEAD is never resolved as the old approval,
and the State is never normalized in place.

`review.verdict` is `pending` in the intermediate repair state: after a
`changes_requested` and an appending `register-plan`, the `review -> implementation`
advance clears the failed verdict to `pending` in one save while preserving
`current_task`, `completed_tasks`, and the completed task-hash prefix, and routes
`next_action` to the first appended task. That intermediate state is valid.
A coherent `changes_requested` with its appending rework Plan already
registered is also valid while still in `review`: only that Plan re-registration
may differ from the failed Review's `plan_sha256` binding, and only while the
completed task contracts are unchanged — never source-code drift or changed
Review bytes. A recorded `pass` never inherits that exception.
`review -> done` requires a current `pass` (verdict `pass`, the Review artifact
hash and `plan_sha256` still matching, and no code drift since the recorded
commit); `validate` reports the same mismatch as an ERROR and a `done` phase
without a `pass` is an ERROR. In `review` the v2 route is `reviewer`, not
`checkpoint-handoff`.

## v2 upgrade and reconstruction

A Ticket is never upgraded in place. `ai-workflow upgrade` upgrades only the
installed protocol (`.ai/workflow/`); it never rewrites a Ticket's `state.yaml`.
Converting one Ticket is the explicit `upgrade-ticket <ticket-id>` command.

`upgrade-ticket` converts one interpretable *active* v1 Ticket to v2 once. It
keeps the phase, source references, counters, ordered completed history and
unknown maps, records the additive `upgrade` block, resets `evidence.gate` to
`insufficient` and `review.verdict` to `pending`, and creates an unresolved
`machine` escalation whose resolver is `workflow-bootstrap` (preserving
`escalation.interrupted_action`). It fabricates no audit, registered Plan or
review pass. A historical `done` Ticket, an uninterpretable `workflow_version`
(boolean, zero, or future), or a state too malformed to reconstruct is rejected
with the State bytes unchanged; an already-v2 Ticket is a byte-preserving no-op.

The conversion records:

- `upgrade.from_version` — the previous version (`1`).
- `upgrade.previous_gate` — the gate in effect before conversion (or `null`).
- `upgrade.requires_reconstruction` — `true` until the senior reconstruction is
  cleared.

While `requires_reconstruction` is true the retained phase's contracts are
unsatisfied by design: `set-gate` and `register-plan` are permitted for the
senior resolver, `validate` reports the reconstruction as an ERROR blocker, and
the escalation resolver is `workflow-bootstrap`. The resolver supplies the
current phase's artifacts through the public commands and clears the flag with
`escalate --clear --resolution ...`. Clearing is atomic: it prepares the
proposed cleared State and checks it against the retained phase's current
contracts (a pending Review is acceptable only with every original task
complete), a current sufficient audit when the phase is decisionward, and a
confirmed adoption checkpoint when the repo is adopted; it then clears the
flag, restores the interrupted Status, and recomputes the phase-appropriate
`next_action` in one save — leaving no continuing out-of-phase write
permission. Registering the reconstructed Plan first binds the absent
historical completed prefix (recording the task hashes while preserving the
numeric history); every later registration must match those recorded
contracts, even while the reconstruction is still active.

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
