# Protocol: Repo-native Cross-Harness Agent Workflow

Canonical sources: the spec `docs/specs/agent-workflow-protocol.md` and ADRs 0001/0002 in the kit repo. This directory is the protocol as installed into a target repository.

## 1. Goal

Any coding agent that can read and write a Git repository (Codex, TRAE, ZCode, ...) can, on entering the repo, determine from a small set of fixed files:

> what task -> which phase -> what evidence exists -> what the next role/action is

without relying on chat history. The repository is the only persistent source of truth for workflow state.

## 2. Core principles

1. The Git repository is the only persistent source of truth for workflow state.
2. `.ai/workflow/` holds the protocol and templates; `.ai/work/<ticket-id>/` holds ticket-level state and artifacts.
3. `state.yaml` is the machine-readable authoritative workflow state — the first file any harness reads.
4. Skills, AGENTS.md managed blocks, and project rules are adapters pointing at this protocol; they never copy protocol content.
5. Never overwrite existing repo documentation; existing specs, tickets, and plans are integrated by reference.
6. All install and migration operations are idempotent, non-destructive, and rollback-capable.

## 3. Entering a ticket

1. Read `.ai/work/<ticket-id>/state.yaml`. It is authoritative; chat history is never authoritative.
2. Note `phase` and `status`. The intended next step is `next_action`.
3. Check `claim`. If another session holds the claim, read `handoff.md` before doing anything.
4. Confirm your role matches `next_action.role` (see ROLES.md). If not, do not act; hand back.

## 4. Phases and statuses

The phase machine is linear with one evidence loop:

```
UNINITIALIZED -> REQUIREMENT -> EVIDENCE_COLLECTION -> EVIDENCE_AUDIT
  -> (evidence insufficient) -> FOLLOWUP_EVIDENCE -> EVIDENCE_AUDIT
  -> TECHNICAL_DECISION -> PLANNING -> IMPLEMENTATION -> REVIEW -> DONE
```

In `state.yaml`, phases are lowercase: `requirement`, `evidence_collection`, `evidence_audit`, `followup_evidence`, `technical_decision`, `planning`, `implementation`, `review`, `done`.

On a `workflow_version: 2` Ticket there is one additional edge: `review -> implementation`, the append-only repair path taken after a `changes_requested` Review. It is not available to v1 Tickets.

Lateral statuses are orthogonal to phase and are never merged into it: `active`, `blocked`, `escalation_required`, `paused`, `abandoned`.

A phase changes only via the transitions above. Do not invent transitions.

## 5. Claim semantics

`claim: {harness, model, claimed_at}` records which session is working on the ticket. It is a soft claim — advisory, not a lock. Set it when you begin a working session. A conflicting session must read `handoff.md` before taking over.

## 6. Reading and updating state.yaml

- Read `state.yaml` before acting; save it after every state change.
- Stamp `updated_at` on every save.
- Write only the restricted YAML subset documented in STATE_SCHEMA.md.
- Unknown fields are silently ignored — never an error, never deleted.
- Reference existing specs, tickets, and plans by path in `source_artifacts`; never copy them into `.ai/`.

## 7. Writing artifacts

Artifact contracts are in ARTIFACTS.md. In brief: evidence.md is the Scout Report, collected by a scout; evidence-audit.md answers only sufficiency questions; decision.md is senior-only; progress.md logs at task granularity per its template (`.ai/workflow/templates/progress.md`: actual changes, verification/results, deviations, unresolved problems); handoff.md has fixed sections plus a Repository State block. Each artifact's writer is defined in ROLES.md.

### Scouting and auditing

A scout turns an engineering request into a bounded, traceable report:

1. Capture the observation snapshot first: current HEAD as `observed_commit` and relevant dirty paths as `dirty_changes`.
2. Record Decision Questions (DQs) tied to the decisions they affect. If the ticket supplies none, draft them from the request. Ambiguity that requires an architectural choice is escalated, not answered.
3. Record findings as FACT / INFERENCE / UNKNOWN with stable F-IDs, precise anchors (file/line/symbol, key/record, or command/result/exit), the verification method, and its scope or limits. Negative searches state their scope and exclusions. INFERENCE cites its basis.
4. Record unresolved DQ/F IDs in Unknowns with decision impact and the next collection step; a critical UNKNOWN does not block report readiness but cannot open the Evidence Gate.
5. Stop when questions are answered or remaining gaps and the need for a new decision or resource are explicit. Write the stopping reason in the report's Handoff. An exhausted budget produces a partial report, not a successful investigation.
6. The scout writes evidence and handoff only — never production changes, final decisions, or its own sufficiency verdict. Necessary temporary diagnostics are permitted; record their outcomes and residual changes.

The evidence-auditor reads the report and answers the four sufficiency questions in evidence-audit.md, then records the gate. On a `workflow_version: 2` Ticket the recorded verdict is bound to the audited Evidence and its audit artifact: changing either after a sufficient verdict is recorded makes the gate stale, and `validate` and decisionward advances report the same blocker until the auditor re-audits and records the gate again. Report readiness and evidence sufficiency are distinct: a ready report with a critical UNKNOWN still leaves the Gate insufficient until the auditor decides otherwise.

### Registered execution readiness (workflow_version 2)

On a `workflow_version: 2` Ticket an executor may not enter `implementation` or complete a task unless the ticket is genuinely ready. Before the `planning -> implementation` transition and before every `complete-task`, the kit requires:

- a registered Plan (`source_artifacts.plan.path` + `sha256`); a missing or unregistered Plan is rejected;
- Plan byte identity and task-contract (task-hash) identity — changing the Plan or one of its task sections after registration is drift and is rejected;
- coherent counters — non-negative integers only (booleans are never integers), `completed_tasks == [1..current_task]`, `current_task <= total_tasks`, and the registered total matching the task-hash count;
- a current sufficient evidence gate (the fresh gate binding); and
- an active ticket — `blocked`, `paused`, `abandoned`, or `escalation_required` Status may not execute.

When the State marks the repo as adopted (`migration.adopted_existing_repo`), the `adoption_checkpoint` must carry all six confirmation booleans as true — `continuation_safe` included — before an executor proceeds; an adopted but unconfirmed ticket is rejected. `validate` reports the same problems as ERROR findings in `implementation`, `review`, and `done`. Version 1 Tickets are unaffected: every one of these conditions is v2-only. `complete-task` requires `implementation` and the current registered Plan on v2; its optional `--total` cannot override the registered count (a disagreeing value is rejected, not written), and on completion the explicit `next_action.task` is refreshed.

### Review and completion (workflow_version 2)

On a `workflow_version: 2` Ticket the Reviewer owns the Review in an independent context (senior default): it reads `decision.md` and the registered Plan, independently verifies the acceptance criteria against the actual change and the recorded verification results, writes `review.md` (see ARTIFACTS.md), and records the verdict with `set-review`. A mechanical checkpoint-handoff alone cannot supply the technical verdict, so in `review` the route is `reviewer`, not `checkpoint-handoff`.

Completion is gated:

- entering `review` requires a genuinely finished implementation — every registered task complete, the readiness conditions still satisfied, and the required artifacts (`evidence.md`, `evidence-audit.md`, `decision.md`, `handoff.md`) present;
- `review -> done` requires a CURRENT passing Review — `review.verdict == "pass"`, the bound Review artifact unchanged, the bound `plan_sha256` still matching the registered Plan, and no code drift since the reviewed commit. A missing verdict, `changes_requested`, or a stale binding is rejected; `done` is never silently reopened.

A `changes_requested` Review is repaired append-only: the senior registers an appending rework Plan (`register-plan`), and `review -> implementation` clears the failed verdict to `pending` while preserving `current_task`, `completed_tasks`, and the completed task-hash prefix, routing to the first appended task. The repair requires the recorded Review to be unchanged and the reviewed code to still match; a design or architectural change is escalated, never improvised as rework.

### Counter meaning (both versions)

`implementation.current_task` is the number of completed tasks and `implementation.total_tasks` is the registered total. `next_action.task` is the explicit executable task number — `current_task + 1` while `current_task < total_tasks`, and `null` once every task is complete. Initial registration sets `current_task = 0`; entering `implementation` makes `next_action.task` `1`. `status` shows the same executable task without changing the completed count, so State and status use one meaning of "task".

## 8. Escalation

Escalations are recorded in `state.yaml` (`escalation` block) and handled per ESCALATION.md. Two scopes: `machine` (default — resolved by a senior role, never interrupts the user) and `human` (the only scope that interrupts the user).

## 9. Handoff discipline

Before stopping work on a ticket:

1. Update `state.yaml` to reflect the current phase, status, and progress.
2. Write `handoff.md` with the fixed sections and the Repository State block.
3. Run `ai-workflow validate`; no ERROR findings may remain. Any WARN findings are recorded in handoff.md.
4. Leave the working tree interpretable: the next agent must be able to continue from `state.yaml` + `handoff.md` alone.

### Portable continuation

A receiver resumes from persisted state and artifacts, never from chat history:

```
ai-workflow resume <ticket-id>
```

prints a read-only brief with the Ticket, State (phase/status/gate/escalation),
the next role/action/task, the repository branch/HEAD/dirty paths, the referenced
artifacts and their digests, and the continuation checks. It exits `0` for a valid
brief, `1` when the brief carries ERROR blockers or `state.yaml` cannot be read,
and `2` for a usage error; a readable blocked Ticket still prints the brief
(exit `1`). The command never writes `updated_at`, never claims the ticket, and
never mutates a file — it points at reports rather than copying them.

An Evidence report whose `observed_commit` is older than HEAD prompts a relevance
assessment of its anchors; those facts are not automatically discarded. Review
freshness follows the review checks in section 7. Version 1 Tickets print
explicit notices for the newer contracts instead of an invented gate or a
migration claim. Model tiers are Harness-local defaults (see ROLES.md); manual
model/Harness switching is supported and no automatic dispatch is assumed.

## 10. Commits and rollback

- Commit at every phase boundary; during implementation, commit per task.
- Every work commit uses the prefix `ai-workflow(<ticket-id>): <action>`, e.g. `ai-workflow(TICKET-017): task 4 complete`. Grepping `ai-workflow(` recovers the whole work history.
- The phase-boundary commit is both the handoff anchor and the rollback point.
- Recovery from a botched phase: `git revert` to the last phase-boundary commit, then record an `incident` block in `state.yaml` explaining what went wrong and how it was recovered.
- `abandoned` tickets stay on disk and can be resurrected by a senior role: roll back to the last boundary commit, record an incident block, re-claim.

## 11. Legacy adoption

For repos adopted from existing state (existing specs, tickets, plans, half-done work), follow MIGRATION.md: discovery -> migration report -> phase reconstruction -> retroactive minimum evidence -> decision reconstruction -> adoption checkpoint. Never fabricate artifacts for phases that were never executed.

### Explicit version conversion (`ai-workflow upgrade-ticket`)

`ai-workflow upgrade` upgrades only the installed protocol; it never rewrites a Ticket's `state.yaml` and never promotes its `workflow_version` in place. Converting a Ticket is explicit: `upgrade-ticket <ticket-id>` converts one interpretable active v1 Ticket to `workflow_version: 2` once, keeping its phase and history, resetting the gate to `insufficient` and the review to `pending`, and recording `upgrade.requires_reconstruction` together with an unresolved machine escalation whose resolver is `workflow-bootstrap` (preserving the interrupted `next_action`). It fabricates no audit, Plan or review pass, and a historical `done` Ticket stays v1. The converted Ticket is not valid until a senior resolver reconstructs the retained phase's current contracts through the public commands and clears the flag with `escalate --clear --resolution`. See MIGRATION.md and STATE_SCHEMA.md.
