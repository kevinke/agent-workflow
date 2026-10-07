# Decision Scout hardening: review follow-up spec

Status: ready-for-agent
Date: 2026-10-08
Parent: [Decision Scout baseline](../decision-scout-port/spec.md)
Evidence: [post-implementation review](../decision-scout-port/post-implementation-review-2026-10-08.md)
Disposition: [finding-by-finding decisions](review-disposition.md)
Delivery: [nine tickets](tickets.md)
Plans: [development plan](../../docs/superpowers/plans/2026-10-08-scout-hardening.md)

## Problem Statement

The shipped workflow has demonstrated real cross-Harness implementation and
independent review. However, a mutable Review identity and a Git index race can
let changed code retain a pass. Ordinary senior resolution and late-phase
adoption can leave an executor permanently blocked. Upgrade can lose extension
fields, and a committed artifact archive can lose the raw bytes its State binds.
Some structured reports and handoffs also pass validation while lacking the
concrete information a receiving model needs.

These defects weaken the user's intended inexpensive Scout → senior decision →
bounded executor workflow. The pilot used the same reported model for scouting
and decision work, so that particular model pairing still needs direct evidence.

## Solution

Keep the existing repo-native protocol and structured artifacts. Repair current
snapshot checks, make senior recovery a supported path, preserve artifact and
extension data, and enforce narrowly defined syntactic contracts. Put the rules
in the Protocol and artifact contracts; role Skills and Harness adapters remain
short entry points. Supplement the pilot with a distinct Scout/decision model
pair after these repairs; keep the original pilot completion and raw logs.

## User Stories

1. As a reviewer, I want the recorded commit to be immutable, so that a later HEAD cannot change what I approved.
2. As a receiver, I want both pass and changes_requested checked against their reports and code, so that stale findings cannot route work.
3. As an executor, I want a same-size dirty edit detected even with coarse file timestamps, so that review gates remain trustworthy.
4. As a receiver, I want resume to leave the index and artifacts untouched, so that reading a handoff cannot change repository state.
5. As a senior resolver, I want to re-audit Evidence and re-register a Plan while escalation is active, so that recovery does not require hand-editing State.
6. As an adopter, I want a late-phase start to enter an explicit recovery mode, so that missing contracts are rebuilt before execution.
7. As a senior resolver, I want clear rejected until the retained phase is coherent, so that resolution cannot re-enable a broken executor.
8. As a ticket owner, I want completed task identities and paused/blocked status preserved, so that reconstruction does not fabricate progress.
9. As an integrator, I want unknown nested fields preserved on upgrade, so that my extensions survive conversion.
10. As a user, I want malformed supported input rejected without a traceback or partial write, so that I can correct it safely.
11. As a senior decision maker, I want code facts anchored to file, line and symbol, so that I can verify targeted facts instead of repeating broad exploration.
12. As a Scout, I want runtime, configuration, inference and scoped negative-search evidence supported, so that useful findings need not invent code anchors.
13. As an auditor, I want concrete metadata and resolvable question/fact references, so that a syntactically empty report cannot open a gate.
14. As a receiver on another platform, I want bound raw bytes preserved through commit, checkout and export, so that line-ending conversion does not invalidate an audit.
15. As an archivist, I want verified raw artifacts packaged with a manifest, so that historical bindings can be checked after a fresh clone.
16. As an implementer, I want draft handoffs permitted early and concrete handoffs required at transfer boundaries, so that scaffolds cannot masquerade as completed work.
17. As a Skill maintainer, I want one authoritative source for semantic rules, so that different Harnesses do not follow conflicting copies.
18. As a Windows user, I want the observed launch diagnostic documented with its limits, so that a policy rejection is distinguished from a review result.
19. As a workflow owner, I want a distinct inexpensive Scout/senior decision pair measured on a bounded task, so that actual model allocation is demonstrated.
20. As a budget owner, I want missing telemetry reported as UNKNOWN, so that tool-call counts are not presented as monetary savings.

## Implementation Decisions

### C0 — Compatibility and authority

- Keep `workflow_version: 2`, `schema_version: 1`, Python 3 stdlib only and the existing restricted YAML parser.
- Keep v1 Ticket behavior and historical pilot completion unchanged.
- Keep v2 SHA-256 over original artifact bytes; do not normalize line endings before hashing.
- Protocol and artifact contracts own semantic rules; Skills and adapters point to them.
- Structural validation establishes conformance, not the truth of natural-language claims or model seniority.

### C1 — Immutable, current Review identity (HARDEN-001)

Review metadata accepts a literal hexadecimal Git object ID, full or an
unambiguous abbreviation of at least seven characters, resolving to a commit
ancestor of the current HEAD. Store the full resolved object ID in State for
both verdicts. Reject HEAD, branch and tag names, including refs that resolve
successfully. Support the repository's actual Git object format.

A previously stored moving ref is stale and needs a new independent Review;
do not resolve today's HEAD and claim it was the old approval. Check artifact
hash, immutable reviewed commit, relevant code drift and registered Plan binding
for pass and changes_requested in validation, resume and mutation guards.
Pending remains a valid intermediate verdict. Appended rework may retain the
failed Review's old Plan identity only when the completed task prefix is
unchanged and the existing explicit repair contract is satisfied. Recorded
pass may not inherit this exception.

### C2 — Race-safe read-only code drift (HARDEN-002)

Dirty code, tests and fixtures remain relevant even when bytes have the same
length and timestamps collide with the index's cached stat information. Make
the copied-index Git assessment honor racy-stat detection without changing the
original index, index timestamps, State or artifacts. Cover staged, unstaged,
untracked and deleted paths under existing relevant-path rules. A sleeping or
retrying test is not the repair.

### C3 — Recoverable senior resolution and bootstrap (HARDEN-003)

Recognize three bounded recovery contexts: ordinary unresolved escalation,
explicit v1 upgrade reconstruction, and v2 late-phase bootstrap. New start/adopt
at implementation or review establishes bootstrap recovery and senior routing,
retains the requested phase, and cannot become executor-ready merely because
files exist. Older half-ready v2 Tickets can enter ordinary recovery with the
existing escalation command.

In these contexts allow senior re-audit and Plan registration outside their
ordinary phases, while continuing to block routine execution and forward
transitions. This is a workflow condition, not model authentication. Preserve
completed task contracts and counters: unbound historic tasks may be bound once
during reconstruction; subsequent registrations must preserve that prefix.

Clear requires a referenced resolution and checks a proposed restored State
against the retained phase's current artifact, gate, Plan, counter, adoption and
recorded Review contracts before saving anything. Restore paused/blocked status
without claiming it is executable. Pending Review is allowed when all original
tasks are complete. A valid changes_requested append may clear into the review
repair path even while the appended tasks await execution. No arbitrary backward
phase jump, fabricated verdict or reset of completion history is allowed.

Use shared phase/artifact checks for validate and recovery; extract only the
checks needed for this behavior, not a general validation framework.

### C4 — Lossless explicit upgrade (HARDEN-004)

Preserve unknown keys in every existing nested mapping, including upgrade
metadata. Validate the shape of supported maps, version/status/phase fields and
counters before constructing or saving conversion. Malformed but parseable
input returns a normal actionable error without a traceback or file change.
Already-v2 remains a byte-preserving no-op; historical done v1 remains v1.

### C5 — Traceable structural Evidence (HARDEN-005)

A code source requires a repository-relative path, positive line or ordered line
range, and a named symbol/key, or an explicit justified file-scope anchor when
no named symbol exists. Line or symbol alone is insufficient. Configuration or
data sources require a locator and key/record. A runtime source records command,
input, observed result and integer exit status. A scoped negative search records
scope, exclusions and result. Inference cites existing Fact IDs as its basis;
UNKNOWN records what is unobserved and what would establish it. These are the
supported source families; arbitrary unlabelled claims cannot count as Sources.

ANSWERED questions cite at least one existing F-ID. Each finding cites at least
one existing DQ-ID; INFERENCE cites at least one existing F-ID in Basis. UNKNOWN
questions may explicitly say UNKNOWN without an answered Fact, but must describe
the missing observation and collection target. Reject dangling and empty
references, not justified negative or unknown results.

Evidence observed_commit is a concrete full or unambiguous abbreviated object
ID, created_at is ISO-8601, model/Harness fields are non-placeholder strings,
dirty_changes is a string list, and Evidence/Audit rounds are positive integers
excluding booleans. Audit round must equal the gate command and Evidence round.
Do not add online model authentication or require every source file to still
exist at today's HEAD; relevance remains the senior reader's job.

### C6 — Durable raw-byte transport (HARDEN-006)

Protect work-artifact paths from Git text normalization in new installations;
preserve existing user attributes and expose effective attribute conflicts as
read-only transport warnings. A referenced Plan outside that protected scope
needs an explicit per-path attribute before portable checkout. Do not change
global Git configuration or silently widen a user's attributes.

Add explicit `archive-artifacts` export for a v2 Ticket with current bound
Evidence, Audit, Plan and recorded Review. Store original bytes plus a versioned
manifest containing Ticket ID, snapshot HEAD, repository-relative member paths,
computed raw hashes and existing State-bound hashes. The ZIP output is the only
write. Refuse stale bindings, unsafe paths, duplicate members and overwritten
outputs; reject without changing sources, State or leaving a partial archive.
An export preserves artifacts and their identities; it does not supply missing
code history, prove acceptance or automatically authorize another repository.

Package the existing pilot's verified bound bytes without re-gating or altering
historical State. Verify the package after a fresh clone; if original bytes are
unavailable, record the limitation and do not invent replacements. This fixes
historical archive durability while retaining the Markdown/log record.

### C7 — Phase-aware Handoff readiness (HARDEN-007)

The existing Handoff sections and Repository State fields must contain concrete
values at review entry, review/done continuation, late-phase recovery clear and
completion. For that recovery clear, implementation also requires a concrete
handoff. Draft scaffolds earlier in the lifecycle remain permitted with notices.
Reject unchanged template tokens and whole-field angle-bracket placeholders,
including placeholder bullets within required structured sections. Accept
explicit None, justified N/A, code comparisons and useful literal angle brackets.
Do not infer acceptance or verify narrative truth from these syntax checks.

### C8 — Thin role entries and Windows diagnostics (HARDEN-008)

Retain triggers, authoritative links and minimal public-command instructions in
role Skills. Remove copied quotas, gate policy, State field contracts and task
rules. Adapter instructions route to installed Protocol/roles and migration
sources. Document the pilot's observed Windows policy rejection and the local
launch setting that fixed it with read-only intent, diagnostic commands and
stop conditions. Treat it as one observed host-specific solution, not a global
setting or universal fix. Do not automatically retry blocked model sessions or
weaken permissions.

### C9 — Distinct-model paired pilot (HARDEN-009)

Run a bounded, nontrivial disposable task using an actual inexpensive Scout and
a different senior decision model. Record role and actual model/Harness identity
separately. The senior receiver starts with persisted artifacts in a fresh
context and uses resume first; demonstrate at least one actual cross-Harness
Scout-to-decision transfer plus independent fresh-context review.

Record DQ/F anchors, decisions, receiving targeted rereads versus repeated broad
exploration, revisions and telemetry provenance. Keep unavailable measurements
UNKNOWN and make no savings percentage without a comparable baseline. Publish
the experimental result even if the workflow fails; passing needs both credible
artifacts and completed behavioral acceptance, not just successful validation.
Real sessions require an available explicitly authorized budget at execution;
the old exhausted pilot allocation is not reused. This ticket's runbook can be
prepared now; its live acceptance remains pending until the run actually occurs.

## Testing Decisions

Use the existing public-command temporary-Git-repository seam for binding,
recovery, upgrade, report conformance and archive behavior. Assert exit codes,
persisted fields and byte preservation rather than exact error prose. Use a
controlled copied-index experiment to force timestamp equality without sleeps,
then exercise that dirty edit through set-review, done and resume. Existing
lifecycle and installed-kit tests protect v1 behavior and command agreement.

Test raw bytes through commit and fresh checkout with both autocrlf settings,
including mixed line endings and an external Plan. Check archive bindings after
a fresh kit clone and refuse drifted/unsafe exports. Contract fixtures include
valid negative search, runtime, UNKNOWN and justified file-scope cases, not only
rejection examples. Role cleanup uses existing installer/lint tests and manual
rule-source review; do not add tests that just mirror prose.

Run focused tests per code slice, then the complete existing unittest suite at
integration. Prior review evidence contains a real intermittent failure, so a
single rerun passing cannot close C2. Manual pilot evidence complements automated
tests and never substitutes for them. Planning itself does not claim new tests
or fixes have passed.

## Out of Scope

- Runtime implementation, commits, pushes or billable pilot sessions during this documentation request.
- Changing v2 raw-byte hash semantics or normalizing historical digests; a future canonical-hash version needs a separate migration design.
- New model dispatcher, Work Packet workflow, permanent repository map, UI, database or permission system.
- Automatic proof of fact truth, acceptance, model tier or cost savings.
- A broad validation rewrite, reopening original completed tickets or replacing their historical plans.

## Further Notes

The [disposition table](review-disposition.md) distinguishes existing bugs from
clarified/new contracts. Existing review, preservation and traceability promises
remain requirements; they do not become optional enhancements because a pilot
passed. New archive export and distinct-model supplementation are explicit
follow-up scope. Implementation details and file ownership live in the plans.
