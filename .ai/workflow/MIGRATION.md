# Legacy Adoption Procedure (`ai-workflow adopt`)

Adopting an existing/legacy repo (or a half-done ticket inside one) into this
workflow. This is the authority referenced by the `workflow-bootstrap` skill and
driven by a senior model. The `adopt` CLI command performs the mechanical first
steps (discovery and the migration report); every judgment step below is done by
a senior model using the CLI's output.

Read `PROTOCOL.md` and `STATE_SCHEMA.md` first. Never fabricate artifacts for
phases that were never executed; never require re-walking full history.

## When to use

- Fresh repo with no prior workflow state (case A).
- Existing repo, no active ticket (case B).
- Existing repo with a half-done ticket (case C) — the priority.

On a current (v2) install, `adopt` scaffolds the Ticket with
`workflow_version: 2` and all six checkpoint booleans `false`; on an unupgraded
v1 install it stays v1. Adoption itself never fabricates contracts for phases
that were never executed. An adoption (or `start`) directly at
`implementation`/`review` additionally enters explicit bootstrap recovery — see
"Late-phase start/adopt (bootstrap recovery)" below.

## Procedure

### 1. Discovery

Scan the repo and record repository facts (not conclusions): `AGENTS.md`,
`README`, `docs/`, specs, tickets, plans, any existing Matt/Superpowers or
`AGENTS.md` workflow artifacts, and git state (branch, HEAD, commits, diff,
uncommitted files, tests).

The `adopt` CLI does this scan and writes the result to the migration report
(step 2). A senior reviews and corrects it before trusting anything.

### 2. Migration report

Produce `.ai/migration-report.md` at the repo root. It lists the discovery facts
and the required next steps. The report is a snapshot of the repo at adoption
time; it is never a substitute for `state.yaml`, which remains authoritative.

### 3. Phase reconstruction

Reconstruct the phases the repo has already passed through. For each completed
phase in `state.yaml` `historical_phases`, mark one of:

- `confirmed` — a phase completed prior to adoption, supported by evidence
  anchors (source artifacts, git history, code).
- `inferred` — a phase reasonably deduced to have happened, without direct
  evidence.
- `existing` — an artifact for the phase is present on disk but unverified.
- `not_performed` — the phase was never executed here.

Assign `confirmed` only when anchors exist. Never label a phase without
justification. The CLI scaffolds every phase as `not_performed`; a senior sets
the true value with anchors during this step.

### 4. Retroactive minimum evidence

Collect only the evidence needed to safely continue the remaining work — never a
full historical reconstruction. Write it into `evidence.md` using the standard
FACT / INFERENCE / UNKNOWN contract. The file must carry an explicit **Migration
Notice** stating that it is retroactive minimum evidence, not a reconstruction
of history. Do not re-walk the whole repo; collect the minimum that lets the next
role proceed.

### 5. Decision reconstruction

Reconstruct `decision.md` only to the extent the current work still needs it:
extract and re-record only still-valid API / schema / invariants / architecture
decisions that affect remaining work. Do not re-derive decisions that no longer
matter. The reconstruction carries a **Provenance** section recording where these
decisions were extracted from, so readers know they are inherited, not newly made.

### 6. Adoption checkpoint

`state.yaml.adoption_checkpoint` gates whether the ticket may be handed to a
cheap executor. Set all six fields:

- `repository_understood`
- `active_ticket_identified`
- `current_phase_identified`
- `remaining_work_identified`
- `critical_invariants_identified`
- `continuation_safe`

`continuation_safe` stays `false` until a senior confirms the other five items
are true. Only when `continuation_safe: true` may the ticket proceed to a cheap
executor (`ticket-executor`). If any item is not confirmed, a senior resolves the
uncertainty first; escalate via `state.yaml.escalation` if the gap cannot be
closed in-repo.

## Late-phase start/adopt (bootstrap recovery)

On a current (v2) install, starting or adopting a Ticket **directly at**
`implementation` or `review` — `start <id> --phase <phase>` /
`adopt <id> --phase <phase>` — creates explicit bootstrap recovery instead of a
half-ready active State. The scaffold:

- keeps the requested phase (`phase` is never silently changed) and preserves
  the `source_artifacts` references;
- records `recovery.kind: bootstrap` (an additive marker; unknown keys are
  never removed);
- records an unresolved `machine` escalation with the previous Status
  (`active`) and the interrupted ordinary continuation
  (`escalation.previous_status` / `interrupted_action` / `interrupted_phase`);
- locks the Status to `escalation_required` and routes `next_action` to the
  `workflow-bootstrap` senior resolver.

It fabricates no `upgrade` conversion facts: a freshly created v2 State never
carries an `upgrade.from_version` key — only a real v1 conversion
(`upgrade-ticket`) does.

**Initialized files are not ready contracts.** The scaffolded `evidence.md` /
`handoff.md` / `progress.md` are placeholders; there is no audit, registered
Plan or `decision.md`. The Ticket is `escalation_required`: routine advance,
task completion and a raw status overwrite are rejected, and `resume` names the
`workflow-bootstrap` resolver with the unresolved escalation.

The senior resolves it through the public commands, in any order that produces
the retained phase's current contracts, then clears:

1. Audit the Evidence and bind it (`set-gate` — permitted outside
   `evidence_audit` while the recovery is active).
2. Register the Plan (`register-plan` — permitted outside `planning` while the
   recovery is active). For a `review`-phase bootstrap the reconstructed
   completion history must be recorded before the clear; a pending Review is
   clearable only with every registered task complete.
3. Reconstruct `decision.md` for the retained phase.
4. For an adopted repo, confirm all six `adoption_checkpoint` items
   (`continuation_safe` last).
5. Clear with a referenced resolution: `escalate --clear --resolution ...`.
   The clear is atomic: it checks the proposed restored State against the
   retained phase's contracts and saves once; a rejected clear changes no
   State bytes. On success the Ticket resumes its retained phase — ordinary
   execution at `implementation`, the pending review at `review` — and the
   cleared recovery grants no further out-of-phase permission.

Existing half-ready v2 Tickets (created before this contract, without the
`recovery` marker) are not retro-fitted: they enter the same checked recovery
through the ordinary `escalate` command.

## Explicit Ticket reconstruction (`ai-workflow upgrade-ticket`)

`ai-workflow upgrade` upgrades only the installed protocol; it never rewrites a
Ticket's `state.yaml` and never promotes a Ticket's `workflow_version` in place.
Converting a Ticket is a separate, explicit act: `upgrade-ticket <ticket-id>`
converts one interpretable **active** v1 Ticket to `workflow_version: 2` once.

The conversion preflights the State (`upgrade.conversion_problems`) before it
writes anything. Malformed input — a scalar or list where an owned map belongs,
a malformed nested source reference, or boolean/negative implementation counters
without an ordered completed history — is reported distinctly from an
unsupported conversion (a version that cannot be interpreted (boolean, zero, or
future), a historical `done` Ticket, or a Status that is not
active/paused/blocked); both are rejected with an actionable error and the State
bytes unchanged, and an already-v2 Ticket is a byte-preserving no-op.

The conversion then deep-copies the parsed State and merges only its owned keys
into the existing nested maps. Unknown fields everywhere — including unknown
children of the owned maps (`upgrade`, `evidence`, `review`, `escalation`,
`source_artifacts.plan`, `implementation`) and nested custom maps — survive
conversion exactly: they are never checked against owned-field rules, and never
coerced or dropped. The conversion keeps the phase, source references, counters
and ordered completed history, records the additive `upgrade` block
(`from_version`, `previous_gate`, `requires_reconstruction`), resets the gate
to `insufficient` and the review to `pending` (a recorded verdict or gate is
never carried over as old success), and creates an unresolved `machine`
escalation whose resolver is `workflow-bootstrap`, preserving the interrupted
`next_action`. It fabricates no past audit, registered Plan or review pass.

A converted Ticket is `escalation_required` and not yet valid: the retained
phase's current contracts must be reconstructed before it can continue. The senior
resolver supplies them through the public commands (`set-gate`, `register-plan`,
and the required artifacts), then clears the reconstruction with
`escalate --clear --resolution ...`. The unresolved reconstruction is a bounded
recovery context: `set-gate` and `register-plan` are permitted outside their
ordinary phases while it is active, and the allowance ends with the clear. The
first registration of the reconstructed Plan binds the absent historical
completed prefix (it records the completed task hashes while preserving the
numeric history); every later registration must match those recorded contracts,
even while the reconstruction is still active. The clear is atomic: it prepares
the proposed cleared State and checks it against the retained phase's current
contracts (a pending Review is acceptable only with every original task
complete), a current sufficient audit when the phase is decisionward, and a
confirmed adoption checkpoint when the repo is adopted — a rejected clear
changes no State bytes. See `STATE_SCHEMA.md` for the exact `upgrade` fields.

## Rules that never bend

- Never fabricate artifacts for phases never executed.
- Never require re-walking full history (retroactive minimum evidence only).
- Never overwrite existing Matt / Superpowers / AGENTS.md / repo docs; integrate
  existing spec / ticket / plan by reference in `source_artifacts`, never copy.
- `adopt` is idempotent and rollback-capable: re-running it is a no-op and it
  never deletes or overwrites existing files.
- `continuation_safe: false` until a senior confirms the checkpoint.