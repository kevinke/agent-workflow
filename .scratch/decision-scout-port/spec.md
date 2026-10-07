# Spec: Decision Scout and Structured Model Handoff

Status: ready-for-agent
Type: spec
Date: 2026-10-07
Delivery: v2 baseline and live cross-Harness pilot delivered; review follow-up planned.
Follow-up: [hardening spec](../decision-scout-hardening/spec.md).

## Problem Statement

The user wants to pair inexpensive and senior models and continue work across
Harnesses. Senior-model sessions spend too much effort searching, reading files,
tracing references, and reconstructing earlier work. An inexpensive Scout should
perform that legwork and leave a report usable for decisions with only targeted
verification.

The existing Workflow Protocol persists State and separates roles, but its
Evidence contract is too loose to produce consistently useful reports. Execution
and review contracts leave judgment implicit, and some documented safeguards
are not enforced by the CLI.

## Solution

Keep the repo-native Workflow Protocol and thin Harness Adapters. Make a
decision-focused, traceable Scout Report the first usable increment, then add
structured execution contracts and enforce the conditions for continuing,
escalating, reviewing, and completing a Ticket.

The normal collaboration is: inexpensive Scout gathers evidence; a senior role
audits uncertainty, decides, and plans; an inexpensive executor implements a
bounded task; an independent Reviewer verifies the change. Role and model are
separate: harder investigation or implementation can use a senior model, and
several logical phases can share a session.

Success means reduced repeated exploration and reliable continuation, rather
than a promise that downstream models never need another tool call.

## User Stories

1. As a user, I want inexpensive models to explore the repository, so that
   senior-model effort is concentrated on decisions.
2. As a Scout, I want Decision Questions tied to affected decisions, so that
   I know which evidence is worth collecting.
3. As a Scout, I want to draft questions when none are supplied, so that a
   small task can start without a mandatory senior-model call.
4. As a Scout, I want to escalate ambiguity that changes the search direction,
   so that I do not silently choose an architecture.
5. As a decision-maker, I want Fact IDs and file/line/symbol anchors, so that
   I can inspect pivotal claims without surveying the repository.
6. As a decision-maker, I want facts, inferences, and unknowns distinguished,
   so that an earlier guess does not become an established premise.
7. As a decision-maker, I want verification methods and limits, so that static
   reading is not mistaken for runtime verification.
8. As an auditor, I want critical unknowns tied to decisions, so that assigning
   every question a status cannot alone open the Evidence Gate.
9. As a Scout, I want explicit stopping conditions and search exclusions,
   so that I stop when more investigation will not affect a decision.
10. As a user, I want task-specific report sections, so that simple work does
    not require filling irrelevant chapters.
11. As an executor, I want allowed changes, protected behavior, acceptance
    criteria, and verification instructions, so that I need not invent design.
12. As an executor, I want a registered Plan and explicit next task, so that a
    completed-task count cannot be mistaken for an executable task index.
13. As a user, I want escalation to stop execution and route to a senior role,
    so that unresolved design uncertainty cannot be ignored.
14. As a Reviewer, I want actual changes and verification records, so that I
    can judge conformance independently of the implementer's summary.
15. As a user, I want completion to require current passing review, so that a
    phase label alone cannot declare work finished.
16. As an executor, I want review findings turned into explicit rework tasks,
    so that repairs have a normal continuation path.
17. As a receiving Agent, I want a concise continuation brief, so that I can
    resume without the previous chat.
18. As a receiving Agent, I want report and review freshness distinguished,
    so that old evidence is neither blindly trusted nor needlessly discarded.
19. As a user, I want existing Tickets preserved during upgrade, so that new
    contracts do not fabricate historical compliance.
20. As a user, I want a real cross-Harness pilot, so that I can assess savings,
    repeated exploration, and rework.

## Implementation Decisions

### 1. Rule source and release stages

ADR-0001 remains in force: Workflow Protocol rules and templates are repo-native;
Skills and Harness rules route to them. Reuse Evidence and source Plan artifacts
rather than introducing a parallel facts directory or Work Packet system. The
first Scout-contract slice is usable with workflow version 1.

Stricter gates use workflow version 2, retaining schema version 1 and the
restricted YAML subset. Version 1 Tickets retain their semantics until explicitly
upgraded. Installed protocol version and each Ticket's workflow version are
distinct. Unsupported future versions fail clearly instead of using v1 rules.

The new contract remains opt-in through explicit v2 fixtures during the gate
slices. The complete installation/upgrade slice changes the shipped default;
it does not publish a partial v2 workflow between those slices.

### 2. Scout Report contract

Use Evidence as the Scout Report, retaining collection rounds and Migration
Notices. Required sections: Metadata, Decision Questions, Findings, Unknowns,
and Handoff. Optional sections: Reproduction, Execution Path, Failure Boundary,
Contracts, Constraints, and Change Surface. Bug investigations record reproduction
and failure-boundary outcomes, with reasons when they could not be established.

Metadata includes report format version, Ticket identity, observed repository
commit, relevant working-tree changes, collection time, and Scout provenance.
Task type is descriptive report metadata, not a new State enum in this increment.
Historical rounds and Fact IDs remain addressable.

Each Decision Question has a stable DQ ID, question, decision affected, likely
evidence targets, answer status, and linked Fact IDs or an explicit unknown.
Three to eight questions is guidance, not a quota. Scouts may draft initial
questions from the request and add factual follow-ups. Ambiguity requiring an
architectural choice is escalated.

Each important finding has a stable F ID, FACT/INFERENCE/UNKNOWN tag, one precise
statement, associated DQ IDs, sources, verification method, and scope or limits.
Code-derived FACTs identify repository-relative file, line or line range, and
symbol when one exists; configuration/data anchors identify a key or record.
Runtime-derived FACTs record command, relevant input/fixture, observed result,
and exit status. Referenced logs are portable artifacts. Inferences cite their
basis; unknowns explain their decision impact and how to resolve them.

FACT means an observed claim, not a confidence score. Static reading, execution,
and test verification are distinguished. Optional confidence grades cannot replace
evidence. Negative searches record scope and exclusions.

Handoff lists established Fact IDs, decisions still required, precise missing
evidence, areas already investigated, and the stopping reason. Report readiness
and evidence sufficiency are distinct: a report with a critical UNKNOWN can be
ready for audit while the Gate remains insufficient. Scouts write evidence and
handoff, rather than production changes, final decisions, or their own verdict.
Necessary temporary diagnostics are permitted; outcomes and residual changes
are recorded.

### 3. Evidence audit and search bounds

Keep the auditor's four sufficiency questions. Assess DQ coverage, traceability,
verification limits, and decision-changing unknowns within those questions.
Remaining unknowns must be resolved or explicitly shown not to affect the
selected decision before the Gate opens.

For v2, set-gate requires a non-placeholder Evidence report and audit artifact,
and binds the verdict to the SHA-256 of audited Evidence and its audit artifact.
Changing either artifact makes the gate stale and prevents decisionward
transitions until re-audited. Repository
changes do not erase historical facts; a senior evaluates their relevance.

Structural validation checks required sections, IDs, references, tags, metadata,
and anchor presence. It does not prove claims or judge designs. Senior roles
verify pivotal claims when risk warrants it. Search stops when questions are
answered or remaining gaps and the need for a new decision/resource are explicit.
Exhausted budget produces a partial report, not a successful investigation.

### 4. Referenced execution contract

The Plan remains integrated by reference and separate from mutable Progress.
Each ordered task declares objective, input Fact/decision references, allowed
modification scope, protected scope, invariants, acceptance criteria, verification
commands and expected outcomes, dependencies, and escalation conditions.
An explicitly justified not-applicable value is allowed. Open architecture
decisions prevent handing a task to an executor.

Add register-plan with a source path and declared total. It checks structured
task count, stores the reference and SHA-256, initializes counters, and identifies
the next task. For v2, current_task remains the number of completed ordered tasks;
the executable task is current_task plus one, stored in next_action.task.
The initial task is 1, and no executable task remains after the last completion.

Plan registration is allowed in planning, during recorded senior escalation
resolution, and in review when appending requested rework. Completed task
contracts stay unchanged; rework is appended. Executors
cannot silently replace the Plan. V2 rejects missing, unregistered, incomplete,
or changed Plans before implementation or completion recording. The optional
total on complete-task remains compatible but cannot override the registered total.

Progress records completed task, actual changes, verification commands/results,
deviation, and remaining problems. Structural validity is not proof that
acceptance criteria passed.

### 5. Escalation as an execution condition

V2 escalation atomically records scope/reason, changes Status to
escalation_required, retains the interrupted action and previous Status, and
routes next_action to a senior resolver. Evidence phases route to evidence-auditor;
technical decision, planning, implementation, and review conflicts route to
technical-decision; requirement/adoption uncertainty routes to workflow-bootstrap.
Human escalation retains a senior next action to obtain the user's answer and
never resolves that answer automatically.

Routine advances and completion recording are rejected while escalated.
V2 escalate --clear requires a nonempty --resolution describing the senior
resolution and supporting artifact references; it records that resolution with
the clear. Human-scope resolutions reference the user's answer. Clear restores the interrupted
action and previous Status after checking validity; repeat escalation retains
the original continuation. Paused/blocked conditions are preserved. Status edits
cannot bypass escalation. Evidence/Plan changes use their normal audit/registration
paths before execution resumes.

These are protocol consistency checks, not authentication of model identity or
a filesystem permissions system.

### 6. Review, completion, and rework

Add Reviewer and Review artifact. Reviewer owns technical conformance;
checkpoint-handoff owns mechanical consistency and transitions. Review uses
an independent context from implementation and defaults to a senior model.
Decision phases may share a senior session; review need not use another vendor.

Review records code commit, registered Plan identity, acceptance-criterion
results, verification commands/results, findings, verdict, and required rework.
Add set-review with pass or changes_requested, binding the verdict to the Review
artifact hash, reviewed code commit, and registered Plan hash. Recording requires
the artifact and coherent completed-task state.

V2 implementation-to-review requires all registered tasks complete, current Plan,
required artifacts, and no escalation. Review-to-done requires current pass.
Require clean reviewed code; inspect changed paths since the reviewed commit;
changes to code, fixtures, tests, or Plan invalidate pass. Changes confined to
this Ticket's State, Progress, Handoff, and Review records do not alone stale code
review, but modifying the bound Review artifact does invalidate its hash.

The reviewed commit must be an ancestor of the current checkout. A different
branch name alone does not invalidate the review; an unrelated code history does.

Add review-to-implementation for changes_requested with registered appended
rework. Return invalidates old review, retains completed tasks, and selects the
first appended task. Architectural findings require escalation before rework
registration; local repairs may stay within the existing decision. A done Ticket
is not silently reopened.

### 7. Portable continuation and model routing

Add read-only resume output: Ticket, Phase, Status, Gate, escalation, next
role/action/task, repository identity/dirty state, artifact references/digests,
validation findings, and precise freshness checks. Point at reports rather than
copying them. V1 Tickets get explicit missing-contract notices.

Handoff adds artifact identity, verification limits, known relevant repository
drift, and blockers. Receivers compare relevant changes against anchors instead
of starting a broad survey. Evidence commit differing from HEAD requires
relevance assessment, not automatic rejection of every fact.

Model tiers are Harness-local defaults. Scouts/executors escalate when tools,
reproduction environment, or task clarity are missing. Manual model/Harness
switching is supported; automatic dispatch and subagent availability are not
assumed. Soft Claims remain advisory.

### 8. Installation and existing Tickets

New v2 Tickets receive templates and pending gates; a scaffold is not a completed
report, audit, decision, or review. Install remains idempotent. Protocol upgrade
updates installed rules without automatically promoting old Tickets.

Add upgrade-ticket for active v1 Tickets. Preserve source references, rounds,
completed tasks, unknown fields, and current phase. Missing contracts become
visible blockers and senior reconstruction work; no pass or historic fact is
invented. Historical done Tickets remain v1 in this increment. Repeating upgrade
is safe; an uninterpretable Ticket is unchanged and produces an error. Adopted
Tickets still need the Adoption Checkpoint before executor handoff.

### 2026-10-08 — Post-implementation contract supplement

The baseline implementation and real bug/feature cross-Harness pilot have been
delivered. The [post-implementation review](post-implementation-review-2026-10-08.md)
found remaining correctness defects and a separate model-pairing evidence gap.
The [hardening supplement](../decision-scout-hardening/spec.md) defines their
current requirements; the [disposition](../decision-scout-hardening/review-disposition.md)
separates existing promises from newly enforced boundaries.

- Review identity must be a stored full immutable OID, with pass and failed
  verdicts assessed consistently; dirty code must remain detectable under
  timestamp/index collisions.
- Ordinary escalation, late-phase bootstrap and upgrade reconstruction need
  a bounded senior recovery path and atomic retained-phase readiness checks.
- Unknown nested upgrade fields and original bound artifact bytes survive
  conversion and transport; v2 retains its raw-byte hash semantics.
- Evidence references/metadata/source locators and late-phase Handoff contents
  have concrete syntactic contracts; independent review still establishes acceptance.
- Skills remain thin pointers to Protocol contracts. A supplemental actual
  cheap-Scout/distinct-senior decision pilot tests the remaining allocation claim.

Exact outcomes, dependencies and development plans are in the
[new ticket index](../decision-scout-hardening/tickets.md). Original SCOUT-001–008
records and plans remain historical; these findings do not erase their results.

## Testing Decisions

Use the public CLI as the primary seam. Extend temporary-repository dogfood
tests, driving commands as a Harness would and checking State, artifacts, output,
exit status, and unchanged State after rejected operations. Reuse parser/mutation
unit tests for exceptional conditions; avoid assertions on helper shapes or
exact narrative prose.

- Scout: bug/feature reports; missing anchors; static/runtime distinctions;
  scoped negative searches; critical unknowns; retained follow-up references.
  A receiving reader should locate pivotal evidence without a general survey.
- Audit: insufficient follow-up, sufficient verdict, placeholders, changed
  Evidence after audit, malformed IDs, missing sources.
- Execution: missing Plan, task-count mismatch, initial task 1, plan drift,
  wrong phase, final completion, append-only rework, and existing counter checks.
- Escalation: atomic routing, blocked completion/advance, human scope, repeat
  escalation, paused/blocked restoration, invalid clear, Status bypass attempts.
- Review: incomplete implementation, no verdict, changed Plan/code/tests after
  pass, allowed workflow-only commits, appended rework, repeated review.
- Resume: read-only output, relevant drift, old report identity, v1 notices,
  and provenance without chat.
- Compatibility: preserved v1 Tickets, explicit upgrade without fabricated
  passes, unknown-field preservation, adoption safety, idempotent install/upgrade.

Record a live pilot on one bug and one small feature using inexpensive scouting,
senior decisions, and an actual handoff between two available Harnesses. Record
models/Harnesses, repeated broad exploration, targeted verification, artifact
gaps, rework, elapsed time, and available usage measurements. Tool-call counts
alone do not establish cost savings; unavailable token/cost data stay unknown.
If Harness/model access is absent, the live pilot remains pending; simulated
CLI sessions are not proof of actual model performance.

## Out of Scope

- Production implementation during this documentation request.
- Automatic model dispatch, new orchestrator, MCP, database, web UI, hard locks.
- Replacing the workflow with standalone Skills or Work Packets.
- Mandatory new DQ artifact, task_type State enum, confidence scores, repository
  maps, or thirteen-section reports.
- Automatic proof of natural-language claims or design quality.
- Arbitrary backward phase jumps or full historical reconstruction.
- Filesystem permission enforcement or global model policy changes.

## Further Notes

The user prioritised inexpensive scouting and traceable structured facts.
The original eight-slice implementation and real cross-Harness pilot are delivered,
as recorded in the appended history and pilot report. The 2026-10-08 hardening
spec, tickets and plans are ready-for-agent; their implementation has not started.
The original release stages are preserved as design history, not a pending
frontier or evidence that all later review findings have been resolved.

Primary sources: [original proposal](original-proposal.md),
[verbatim TRAE analysis](fit-analysis.md), and
[preserved pre-spec synthesis](design-history.md).
Original gaps: [review-findings.md](review-findings.md).
Current review: [post-implementation review](post-implementation-review-2026-10-08.md).
Delivery frontier: [ticket index](tickets.md).
Development plans: [shared contracts and eight Ticket plans](../../docs/superpowers/plans/2026-10-07-decision-scout-handoff.md).

## Comments

- 2026-10-07 — Replaced the pre-spec summary after the user prioritised cheap
  Scout work and structured facts. Preserved the old summary in design-history.md
  and left both verbatim sources intact. Review/escalation fixes are later slices.

- 2026-10-08 — Added the post-implementation contract supplement and linked the nine HARDEN follow-up tickets/plans. Preserved prior sources, completion records and pilot history; no runtime fixes are claimed.
