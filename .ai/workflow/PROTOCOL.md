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

New work ships on `workflow_version: 2`: a current install renders its template as v2, so greenfield `start` and `adopt` both begin on the v2 contracts. An existing `workflow_version: 1` Ticket (and an unupgraded v1 install) keeps the frozen v1 semantics until it is explicitly converted with `upgrade-ticket`.

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

On a `workflow_version: 2` Ticket the Reviewer owns the Review in an independent context (senior default): it reads `decision.md` and the registered Plan, independently verifies the acceptance criteria against the actual change and the recorded verification results **inside a prepared isolated snapshot** (section 9, §"Reviewer verification isolation and publication"), authors `review.md` as its own candidate report under that snapshot's scratch area (see ARTIFACTS.md), and has the verdict published by the guarded `set-review`; it writes no live record and performs no live commit. The Review Metadata `reviewed_commit` is a literal hexadecimal Git object ID (full, or an unambiguous abbreviation of at least seven hex digits) resolving to an ancestor of HEAD; HEAD, branch and tag names are rejected even when they resolve, and `set-review` stores the full resolved commit ID once — for `pass` and `changes_requested` alike — so the verdict is bound to the immutable change that was actually reviewed. A mechanical checkpoint-handoff alone cannot supply the technical verdict, so in `review` the route is `reviewer`, not `checkpoint-handoff`.

Completion is gated:

- entering `review` requires a genuinely finished implementation — every registered task complete, the readiness conditions still satisfied, and the required artifacts (`evidence.md`, `evidence-audit.md`, `decision.md`, `handoff.md`) present;
- `review -> done` requires a CURRENT passing Review — `review.verdict == "pass"`, the bound Review artifact unchanged, the bound `plan_sha256` still matching the registered Plan, and no code drift since the recorded commit. A missing verdict, `changes_requested`, or a stale binding is rejected; `done` is never silently reopened.

Both recorded verdicts are re-assessed against their immutable bindings by `validate`, `resume`, and the mutation guards — a `changes_requested` keeps its Review bytes, literal commit, registered Plan and code identity exactly like a `pass`. A previously stored symbolic binding (`HEAD`, a branch or tag name) is stale: it is reported and requires a new independent review, never re-authenticated by resolving today's HEAD.

A `changes_requested` Review is repaired append-only: the senior registers an appending rework Plan (`register-plan`), and `review -> implementation` clears the failed verdict to `pending` while preserving `current_task`, `completed_tasks`, and the completed task-hash prefix, routing to the first appended task. The repair requires the recorded Review to be unchanged and the reviewed code to still match; only the rework Plan's own re-registration may differ from the failed Review's Plan binding, and only while the completed task contracts are unchanged — never source-code drift or changed Review bytes, and a recorded `pass` never inherits that exception. A design or architectural change is escalated, never improvised as rework.

### Counter meaning (both versions)

`implementation.current_task` is the number of completed tasks and `implementation.total_tasks` is the registered total. `next_action.task` is the explicit executable task number — `current_task + 1` while `current_task < total_tasks`, and `null` once every task is complete. Initial registration sets `current_task = 0`; entering `implementation` makes `next_action.task` `1`. `status` shows the same executable task without changing the completed count, so State and status use one meaning of "task".

## 8. Escalation

Escalations are recorded in `state.yaml` (`escalation` block) and handled per ESCALATION.md. Two scopes: `machine` (default — resolved by a senior role, never interrupts the user) and `human` (the only scope that interrupts the user).

On a `workflow_version: 2` Ticket an unresolved escalation is a bounded recovery context: the senior resolver may re-audit Evidence (`set-gate`) and register a corrected Plan (`register-plan`) outside their ordinary phases, while routine execution and forward transitions stay blocked. The same recovery semantics serve a recorded v1→v2 reconstruction (`upgrade-ticket`, `upgrade.requires_reconstruction`). Recovery clear is atomic and checked: it prepares the proposed cleared State and judges it against the retained phase's current contracts before the single save, restores only an allowed previous Status (a restored paused/blocked Ticket is not made executable), preserves completed task identities, and fabricates no verdict — see ESCALATION.md and STATE_SCHEMA.md for the exact contracts.

## 9. Handoff discipline

Before stopping work on a ticket:

1. Update `state.yaml` to reflect the current phase, status, and progress.
2. Write `handoff.md` with the fixed sections and the Repository State block.
3. Run `ai-workflow validate`; no ERROR findings may remain. Any WARN findings are recorded in handoff.md.
4. Leave the working tree interpretable: the next agent must be able to continue from `state.yaml` + `handoff.md` alone.

### Handoff readiness at transfer boundaries (workflow_version 2)

A draft handoff is permitted earlier in the lifecycle; the same readiness problems are surfaced as validate WARN notices there. At the transfer boundaries the handoff must be concrete (`ARTIFACTS.md` defines the syntax): entering `review`, completing to `done`, continuing in `review`/`done` (validate and `resume` report it through the shared phase checks), and clearing an implementation/review recovery. Template tokens, whole-field placeholders and placeholder bullets in the structured sections are rejected at those boundaries; explicit `None` and a justified `N/A — reason` are legitimate where no item exists. Readiness is syntactic: it is not proof that the handoff's narrative is true or that acceptance passed — human review still establishes acceptance.

### Reviewer verification isolation and publication

The reviewer verifies in a disposable snapshot of the immutable reviewed commit
with independent Git metadata. The verification process may write probes,
modified tests, fixtures, caches and generated output only inside that snapshot
or designated scratch/output directories. It may not write live source, tests,
fixtures, configuration or Git metadata, even if it intends to restore them.
Independent context and a final clean diff alone do not establish isolation.

An existing per-session Harness/host boundary must actually deny live writes.
Record its supported scope and demonstrate denial using a disposable protected
sentinel before verification. Copying alone, a prompt-only prohibition or a
restriction the unrestricted verifier can undo is not evidence of enforcement.
Sharing writable Git metadata with the live tree is not an isolated snapshot.
When enforcement is unavailable, report an isolation blocker and escalate;
do not automatically weaken permissions or publish a passing verdict.

Capture the reviewed full commit, separate live/snapshot baseline identities,
and the exact registered Plan/input hashes. Retain artifact raw bytes and path
references; legitimate source checkout newline conversion is not code drift.
Run baseline acceptance independently of any probe-modified tests and record
both scopes: a guarded publication refuses a report whose cited runs do not
distinguish a `baseline` acceptance run from a `probe` run, so both kinds have to
be named and no recorded receipt may go uncited. ARTIFACTS.md owns the
verification-provenance report fields.

The Reviewer authors the technical verdict. A separate, guarded publication
step coordinated by checkpoint-handoff may publish the reviewer's exact report
and update only this Ticket's Review, State and Handoff using public commands.
It supplies no technical judgment and performs no source repair or phase
transition during publication. Re-read the relevant live code, Plan and inputs
before publication; any changed baseline or unavailable currentness check
rejects publication without a new verdict or overwriting existing records.
Relevant dirty code cannot be omitted from the snapshot to obtain approval.
A mismatch requires a fresh snapshot and new independent review.

The index-drift and exact Ticket-record exemptions still apply. Review
provenance cannot prove acceptance or reconstruct past transient writes.
Historical reviews keep their original binding semantics; do not fabricate
isolation claims for them. This is the required procedure, and the public
commands below are what carry it: an ordinary `set-review` on its own performs
no snapshot preparation and no permission enforcement, and it refuses a Review
that carries the reserved provenance section without the guarded options.

#### The commands that carry this procedure

```
ai-workflow prepare-review <ticket-id> --commit <literal-oid> --output <new-directory>
ai-workflow run-review <ticket-id> --review-context <dir> --kind baseline|probe -- <argv...>
ai-workflow set-review <ticket-id> --verdict <pass|changes_requested> \
    --review-context <dir> --report <candidate-review.md> --handoff <candidate-handoff.md>
```

- `prepare-review` is run by the trusted coordinator that also performs the
  guarded publication (`checkpoint-handoff`), never by the reviewer, which works
  only inside the context it produces. It creates a previously absent output
  directory outside the live worktree and Git metadata: an independent clone of
  the literal reviewed commit, raw-byte copies of the registered Plan and of
  every captured verification input, and the supervisor manifest
  (`meta/context.json`) pinning the separate live and snapshot content
  identities. A failure leaves no partial context and changes no live file.
  Preparation counts untracked paths as drift, so a stray generated artifact
  inside scope — the `__pycache__` a verifier command leaves behind is the
  ordinary case — blocks it, because a snapshot of anything other than the
  reviewed commit could not certify the code under review. That fail-closed
  refusal is the design: removing or ignoring the stray artifact and running
  `prepare-review` again is the route to a fresh context, and nothing forces a
  publication past the refusal.
- `run-review` is how a reviewer's command actually executes on the supported
  profile. It runs one verifier command under the enforced `linux-bwrap-v1`
  boundary — `/snapshot` and `/scratch` writable, no live path and no supervisor
  `meta/` mounted at all, a cleared environment, no network, no host sockets —
  captures stdout/stderr, records the command's own exit status plus the residual
  snapshot changes as a supervisor receipt, and exits with that status.
  `--kind baseline` runs are the independent acceptance runs; the first accepted
  baseline is pinned to the prepared snapshot identity, so a probe edit can never
  promote itself into the baseline. `--kind probe` records the declared
  snapshot-relative edits, which stay in the receipt whether or not the reviewer
  restores them. A boundary blocker exits 1 and never falls back to an
  unconstrained run; an unsupported host reports a named blocker instead of
  support. The two host runbooks live in the **ai-workflow source repository**,
  not in an installed target: `adapters/local-review.md` records the host
  actually demonstrated (a Windows coordinator driving `bwrap` through WSL) and
  `adapters/codex/windows.md` records why no **Windows-native boundary** is: no
  Windows or Codex session's own tool-write restriction has been demonstrated on
  the host and build in use. That is a claim about the session's restriction, not
  about the boundary's availability, which the same Windows coordinator
  demonstrates through WSL. Nothing in this procedure depends on opening those
  files from a target repository: the runtime answer for any host is the prepared
  context's own `meta/preflight.json`, which either records an enforced boundary
  or fails closed with a named blocker and no receipt.
- Guarded `set-review` publishes, it does not judge: `--review-context`,
  `--report` and `--handoff` are required together, the report and handoff are
  the reviewer's own candidate bytes written under that context's `scratch/`, and
  the command re-reads the live code, Plan and inputs against the prepared
  manifest before writing. It writes only this Ticket's Review, State and Handoff
  through one journal-guarded transaction; a refusal changes no live record and no
  phase, and every hash pointer it publishes is the reviewer's exact bytes.

Two limits of the published mechanism stay stated rather than implied away:

- A publication consumes its context. `state.yaml` and `handoff.md` are captured
  inputs, so the currentness check refuses a second publication from one prepared
  context: each verdict needs a fresh `prepare-review` run and a fresh
  independent review of anything that changed.
- Journal recovery is deliberately conservative. When an interrupted transaction
  cannot hand its own bytes back, the context stays blocked and there is no
  operator-facing command to clear it; discarding that context and preparing a
  fresh snapshot is the only route, and nothing about that refusal publishes a
  verdict.

The reviewer therefore writes nothing live and performs no live commit.
Publication writes Review, State and Handoff through the public command; the
phase-boundary commit in §"Commits and rollback" belongs to checkpoint-handoff
afterwards, never to the reviewer.

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
