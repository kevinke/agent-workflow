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

## Rules that never bend

- Never fabricate artifacts for phases never executed.
- Never require re-walking full history (retroactive minimum evidence only).
- Never overwrite existing Matt / Superpowers / AGENTS.md / repo docs; integrate
  existing spec / ticket / plan by reference in `source_artifacts`, never copy.
- `adopt` is idempotent and rollback-capable: re-running it is a no-op and it
  never deletes or overwrites existing files.
- `continuation_safe: false` until a senior confirms the checkpoint.