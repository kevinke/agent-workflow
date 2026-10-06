# Decision Scout and Structured Model Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make inexpensive scouting and structured artifacts support reliable decisions, bounded implementation, and continuation across models and Harnesses.

**Architecture:** Keep the repo-native protocol and public CLI. Add small artifact-contract and v2-policy modules behind existing commands; keep Git review checks and read-only continuation separate. Deliver one plan per Ticket, retaining v1 defaults until the complete release slice.

**Tech Stack:** Python 3 standard library, unittest, Markdown, restricted YAML, Git.

**Spec:** [.scratch/decision-scout-port/spec.md](../../../.scratch/decision-scout-port/spec.md)

## Global Constraints

- "ADR-0001 remains in force: Workflow Protocol rules and templates are repo-native; Skills and Harness rules route to them."
- "Stricter gates use workflow version 2, retaining schema version 1 and the restricted YAML subset."
- "Version 1 Tickets retain their semantics until explicitly upgraded."
- "The first Scout-contract slice is usable with workflow version 1."
- "Soft Claims remain advisory."
- "Structural validity is not proof that acceptance criteria passed."
- Python 3 stdlib only; preserve ADR-0002/0003 and current Windows/Linux CI.
- Preserve pre-existing source/test edits. Planning has not implemented any Ticket.
- All file names below are repository-relative; commands run from the kit root.
- Commit only the current task's paths/hunks after checking the staged diff. No push or external publication is prescribed.
- Execute sequentially when tasks share mutation/validation files; dependencies do not grant concurrent write ownership.

## Review Focus

1. Markdown headings inside code fences must not become record boundaries; test in 02.
2. CRLF/Unicode reports and repository paths containing spaces must remain usable; test in 02/03/05.
3. Malformed integer arguments, bool-as-int counters, and future workflow versions must reject without a traceback or State write; test in 02/03.
4. Renames, deletions, staged changes, and untracked tests must invalidate review; test in 05.
5. Migration must not deadlock at a retained late phase, or turn a scaffold into historic evidence; test reconstruction and pending gates in 07.

## Delivery plans

| Ticket | Plan | Blockers |
|---|---|---|
| 01 | [Traceable Scout](2026-10-07-scout-01.md) | None |
| 02 | [Audited Evidence](2026-10-07-scout-02.md) | 01 |
| 03 | [Execution contract](2026-10-07-scout-03.md) | 02 |
| 04 | [Escalation](2026-10-07-scout-04.md) | 02 |
| 05 | [Review/rework](2026-10-07-scout-05.md) | 03, 04 |
| 06 | [Continuation](2026-10-07-scout-06.md) | 05 |
| 07 | [Release/upgrade](2026-10-07-scout-07.md) | 06 |
| 08 | [Live pilot](2026-10-07-scout-08.md) | 07 |

01 is a protocol/template deliverable. 02–06 test explicit v2 fixtures without
changing the default template. 07 changes new Ticket defaults; existing Ticket
versions stay unchanged. 08 is real model/Harness acceptance, not a unit test.

## Current baseline and preflight

HEAD at planning: 5ae8e27fb966d00892c4e4b18aa265840a483389. Existing counter consistency
edits in mutate/validate and their tests are already present; preserve them.
The baseline suite ran on 2026-10-07: **109 tests, OK**.

Before executing, read the spec, this shared contract, and the selected plan.
Inspect git status/diff; arrange isolation at execution time without losing
the spec/plans or pre-existing edits. Never copy only HEAD and assume the
uncommitted planning documents travelled into a new worktree.

Baseline command:
`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts/ai-workflow/tests -q`.

## File responsibility map

| File/module | Responsibility | Introduced by |
|---|---|---|
| .ai/workflow/ARTIFACTS.md and templates | Canonical artifact grammar and role contracts | 01 onward |
| scripts/ai-workflow/contracts.py | Read bounded Markdown/YAML artifacts, validate structure, hash artifacts/tasks | 02 |
| scripts/ai-workflow/workflow_v2.py | Version selection, shared v2 gate/route checks; imports no mutate/validate | 02 |
| scripts/ai-workflow/mutate.py | Load/check/apply/save command transactions; no generic rewrite | Existing |
| scripts/ai-workflow/validate.py | Existing Findings plus shared v2 problems | Existing |
| scripts/ai-workflow/review.py | Git code identity and drift assessment | 05 |
| scripts/ai-workflow/resume.py | Read-only continuation output | 06 |
| scripts/ai-workflow/upgrade.py | Protocol installation version and explicit Ticket conversion | Existing, extended 07 |
| scripts/ai-workflow/tests/v2_support.py | Temporary-repo public-command fixture helpers | 02, extended later |

Keep start/state/parser/status/init/skills as focused existing modules. main.py
owns argument parsing/dispatch; status adds the explicit executable task without
changing completed-task count. Do not introduce a dependency-injection framework.

## Shared implementation interfaces

All these are planned signatures, not currently available APIs.

- contracts.ContractError(Exception).
- contracts.read_artifact(path: str, kind: str) -> dict; result keys are
  metadata: dict, sections: dict[str, str], records: list[dict]. Each Evidence
  record has id, kind (question/finding), fields, and optional tag for findings.
- contracts.sha256_file(path: str) -> str; hash raw bytes, including line endings.
- contracts.validate_evidence(report: dict, ticket_id: str) -> list[str].
- contracts.validate_audit(report: dict, ticket_id: str, gate: str, round_no: int) -> list[str].
- contracts.read_plan(path: str, ticket_id: str) -> list[dict]; each task has
  number: int, fields: dict[str, str], sha256: str. Canonical task hash is SHA-256
  of its section with CRLF changed to LF and trailing whitespace removed.
- contracts.validate_review(report: dict, ticket_id: str, verdict: str) -> list[str].
- workflow_v2.version(data: dict) -> int; missing version means 1 for existing
  fixtures; only integer 1/2 accepted, bool and future/zero versions rejected.
- workflow_v2.problems(root: str, data: dict) -> list[str]; never writes.
- workflow_v2.check_transition(root: str, data: dict, to: str) -> None; raises
  ContractError on failed preconditions. Existing v1 edges plus v2 repair edge.
- workflow_v2.next_action(data: dict, phase: str) -> dict; keys role/action/task.
- mutate.register_plan(root: str, ticket_id: str, path: str, total: int) -> str.
- mutate.escalate(root, ticket_id, scope=None, reason=None, clear=False,
  resolution=None) -> str; existing call forms remain valid on v1.
- mutate.set_review(root: str, ticket_id: str, verdict: str) -> str.
- review.code_drift(root: str, ticket_id: str, reviewed_commit: str,
  plan_path: str) -> list[str]; ContractError for missing Git or unrelated history.
- resume.resume_for_ticket(root: str, ticket_id: str) -> str; read-only.
- upgrade.upgrade_ticket(root: str, ticket_id: str) -> str.

mutate checks version in _load for every mutation, catches ContractError and
raises MutateError before _save. validate
converts shared problems into ERROR Findings. Preserve unknown maps on mutation.
Avoid circular imports: contracts uses parser; review uses contracts; workflow_v2
uses contracts and, after 05, review; validate uses workflow_v2; mutate uses them.

## Artifact grammar frozen for development

Metadata lives in the first fenced yaml block under an exact H2 Metadata heading;
only that block goes through the restricted parser. Other content is Markdown:
do not send commands, generic types, or arbitrary prose through that parser.
Track fences when recognising H2/H3 headings. Duplicate IDs/headings/metadata
keys are errors; extra nonreserved prose sections are allowed.

Evidence Metadata fields: artifact_type=evidence, format_version=1, ticket_id, round,
observed_commit, dirty_changes (string list or []), created_at, scout_harness,
scout_model. Optional task_type/report_status are descriptive. Required H2:
Metadata, Decision Questions, Findings, Unknowns, Handoff.
round is the positive current collection round and must match Audit/CLI round.
Preserve prior DQ/F IDs and collection history when appending follow-up facts.
Before changing the top-level snapshot, retain prior findings' Round, Observed
commit and Dirty changes fields; absent overrides inherit current Metadata.

Under Decision Questions use H3 DQ-01 (two or more digits), with named fields
Question, Decision affected, Evidence targets, Answer (ANSWERED/UNKNOWN), Facts.
Under Findings use H3 F-01 [FACT|INFERENCE|UNKNOWN], with fields Statement,
Questions, Sources, Method, Scope. Additional Basis is required for INFERENCE.
Named fields use `**Label:** value`; multiline lists continue below the label.
Recognise fields outside fences only; accept an explicit UNKNOWN fact-link value
for unresolved questions. A file without a named symbol uses a justified
`:: file scope (no named symbol)` anchor rather than a fabricated function name.
Source lists accept code anchors `code: src/example.py:10-14 :: Example.method`,
data/config anchors with file/line and a named key, and runtime anchors recording
command/input/exit/result. Negative searches additionally state search scope and
exclusions. Method is static/execution/test/inference/unknown. Unknowns names
the unresolved DQ/F IDs, impact, and next collection step; explicit None is valid.

Audit Metadata: artifact_type=evidence-audit, format_version=1, ticket_id, round,
gate, evidence_sha256. Keep exactly the existing four sufficiency-question H2s
after Metadata; each has a substantive answer or justified not-applicable.
Audit SHA-256 is computed when recording the gate, not inserted into itself.

Plan Metadata: artifact_type=plan, format_version=1, ticket_id, task_count.
Use ordered H2 Task 1, Task 2, etc. Each has H3 Objective, Inputs, Allowed changes,
Protected scope, Invariants, Acceptance criteria, Verification, Dependencies,
Escalation conditions. Dependency numbers reference earlier tasks; justified N/A
is valid, bare empty placeholders are not. Inputs reference Fact IDs/decision.

Review Metadata: artifact_type=review, format_version=1, ticket_id,
reviewed_commit, plan_sha256, verdict (pass/changes_requested).
H2 Acceptance results, Verification results, Findings, Required rework.
Passing findings/rework may be explicit None. Metadata verdict must match CLI.

Whole-field scaffold markers, null required values, and empty required answers
are errors at recording/transition time. Requirement-stage scaffolds remain
pending and validate normally. Do not reject legitimate angle brackets inside
real prose or require a full Markdown parser.
Validate incomplete scaffolds as pending during requirement/evidence collection.
Entering evidence_audit requires a ready Evidence report, not a finished audit.
Before set-gate, its default insufficient value is not an audited verdict; the
audit may still be pending. Recording and decisionward continuation require the
concrete reports and current bindings.

## Additive v2 State fields

Retain existing field meanings. Store optional new fields only on v2 Tickets:

- evidence.report_sha256 and evidence.audit_sha256.
- source_artifacts.plan.sha256; implementation.task_hashes is an ordered list
  covering registered tasks; current_task is completed count.
- escalation.previous_status, escalation.interrupted_action (role/action/task),
  escalation.interrupted_phase, escalation.resolution. Keep resolution after clear.
- review.verdict (pending/pass/changes_requested), review.artifact_sha256,
  review.reviewed_commit, review.plan_sha256; artifacts.review defaults to review.md.
- upgrade.from_version, upgrade.requires_reconstruction, upgrade.previous_gate
  during explicit conversion; these are reconstruction facts, not historic passes.

No schema_version bump, new task_type State enum, or copied Plan. Plan paths are
repository-relative and portable; reject nonexistent/outside-root paths including
symlink escapes. Artifact hash identity is byte-based; task-prefix comparison is
canonical-section-based so line-ending conversion alone does not rewrite history.

## Shared test fixture surface

Create tests/v2_support.py in 02, defining V2CLITestCase(unittest.TestCase).
setUp creates a temporary Git repo, one committed code fixture, init/start via
real CLI, and an explicit v2 State fixture. Use environment-only Git identity,
without touching global configuration. Methods:

- cli(*args: str) -> subprocess.CompletedProcess, cwd is temporary target.
- read_state() -> dict; state_bytes() -> bytes; write_state(data: dict) -> None.
- seed_v2(phase: str) -> None; explicit pending state and phase-appropriate route.
- write_evidence(round_no: int = 1) -> None.
- write_audit(gate: str = "sufficient", round_no: int = 1) -> None.
- capture_files() -> dict[str, bytes], excluding Git internals.
- commit_code(path: str, text: str) -> str, returning new HEAD.
- Add in 03: write_plan(total: int = 1) -> str, returning repo-relative path.
- Add in 05: write_review(verdict: str, reviewed_commit=None) -> None.
- Add in 07: seed_v1(phase: str) -> None and prepare_v2_review() -> None.

Evidence sources point at the actual code fixture and its HEAD. Artifact helpers
write valid concrete reports; never hash-fill a gate in order to test that gate's
own success. Later setup binds gates/registers Plans through public commands.
Test methods add sys.path for the kit modules and test support, matching prior art.

## CLI and failure semantics

New commands: register-plan ID --path PATH --total N; set-review ID --verdict
pass|changes_requested; resume ID; upgrade-ticket ID.
Extend escalate --clear with --resolution TEXT for v2. Missing/malformed arguments
exit 2; valid-shaped commands rejected by protocol exit 1; successful mutations
exit 0. Convert numeric arguments at the CLI edge, rejecting bool/nondecimal
counter fields at validation. All rejected mutations preserve State bytes.

resume exits 0 for a valid brief, 1 when the brief contains ERROR blockers or
State cannot be read, and 2 for usage. It still prints a brief for readable
blocked Tickets. Protocol upgrade retains its existing return pair but its second
item becomes []: Ticket versions are handled only by upgrade-ticket.

## Reconstruction rule and limits

upgrade-ticket converts interpretable active v1 State once, keeps its phase and
history, records previous_gate, changes gate to insufficient and review to pending,
and records upgrade.requires_reconstruction. It creates an unresolved machine
escalation with resolver workflow-bootstrap, preserving the interrupted action.
It does not create a past audit, Plan, or review pass. Historical done remains v1.

While this reconstruction is required, set-gate and register-plan are permitted
for the senior resolver at the retained phase. The resolver checks current
Evidence/decision, registers the matching completed-task prefix, and records a
current review if already in review. Clearing requires the current phase's
contracts (pending review is acceptable unless entering done), current sufficient
audit when decisionward, and confirmed adoption if applicable. It clears the
reconstruction flag and restores the checked continuation. Completed task
hashes are first recorded from the reconstructed Plan, preserving numeric history.
State too malformed to reconstruct is unchanged. Existing senior adoption
confirmation remains explicit; this plan does not add a separate adoption CLI.

## Self-review and execution boundary

| Spec coverage | Owning plan/tasks |
|---|---|
| Decisions 1–2; stories 1–3, 5–7, 9–10: portable Scout and fact traceability | 01 Task 1; 02 Task 1 |
| Decision 3; story 8: sufficiency and current audited reports | 02 Task 2 |
| Decision 4; stories 11–12: registered bounded tasks and Progress | 03 Tasks 1–2 |
| Decision 5; stories 4, 13: ambiguity stops execution and routes senior | 01 Task 1; 04 Task 1 |
| Decision 6; stories 14–16: independent current review and appended repair | 05 Tasks 1–2 |
| Decision 7; stories 17–18: manual model/Harness continuation and freshness | 06 Task 1 |
| Decisions 1, 8; story 19: compatibility, adoption and explicit reconstruction | 07 Tasks 1–2 |
| Testing Decisions; story 20: actual paired-model/cross-Harness evidence | 08 Tasks 1–2 |

Every spec decision has an owning Ticket plan, each names exact files,
interfaces, negative cases and commands. Shared interface names are frozen here;
child plans refer to them rather than redefine them. All step checkboxes remain
unchecked. These plans describe future work; the baseline tests alone do not
verify the proposed v2 behavior.

Do not begin implementation in this planning request. Review these artifacts and
select the execution method before invoking an implementation skill.
