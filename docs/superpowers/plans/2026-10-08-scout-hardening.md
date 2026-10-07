# Decision Scout hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the reviewed v2 workflow boundaries and demonstrate the inexpensive Scout → distinct senior model handoff with durable structured artifacts.

**Architecture:** Nine independently reviewable outcome slices keep the existing CLI and protocol. Shared Review identity and retained-phase checks serve mutations, validation and resume; transport preserves current raw hashes. Thin Skills route to those contracts, and the final manual pilot measures the repaired workflow.

**Tech Stack:** Python 3 stdlib, unittest, restricted YAML/Markdown, Git and manually budgeted Harness sessions.

**Spec:** [supplement](../../../.scratch/decision-scout-hardening/spec.md); [review disposition](../../../.scratch/decision-scout-hardening/review-disposition.md).

## Global Constraints

- Keep `workflow_version: 2`, `schema_version: 1`, Python 3 stdlib only and the existing restricted YAML parser.
- Keep v1 Ticket behavior and historical pilot completion unchanged.
- Keep v2 SHA-256 over original artifact bytes; do not normalize line endings before hashing.
- Protocol and artifact contracts own semantic rules; Skills and adapters point to them.
- Structural validation establishes conformance, not the truth of natural-language claims or model seniority.

- No implementation, commits, pushes or real model sessions are performed by this planning deliverable.
- Apply source changes only at execution. Do not copy local machine paths, global permissions or model preferences into project files.
- Shared mutation/validation files have one writer at a time; independent dependencies do not imply parallel writes.

## Review Focus

- Symbolic historical Review values must require fresh review; `test_symbolic_stored_binding_is_stale` in 01.
- Same-size, timestamp-equal dirty code must be detected without index writes; `test_racy_equal_size_edit_is_detected_read_only` in 02.
- A failed Review with appended incomplete repairs must remain recoverable; `test_clear_failed_review_with_appended_repair` in 03.
- Mixed CRLF/LF originals must survive fresh clone/export without changed digests; `test_archive_fresh_clone_keeps_raw_bindings` in 06.
- Actual Scout and decision identities must differ with fresh receiving context; live `PAIR-01` acceptance in 09.

---

## Delivery map and write boundaries

| Slice | Plan | Blockers | Responsibility |
|---|---|---|---|
| HARDEN-001 | [01](2026-10-08-harden-01.md) | None | Review OIDs, verdict binding freshness and callers. |
| HARDEN-002 | [02](2026-10-08-harden-02.md) | None | Copied-index stat correctness and read-only drift regression. |
| HARDEN-003 | [03](2026-10-08-harden-03.md) | 01 | Recovery context, shared phase checks, bootstrap and atomic clear. |
| HARDEN-004 | [04](2026-10-08-harden-04.md) | None | Conversion preflight and recursive extension preservation. |
| HARDEN-005 | [05](2026-10-08-harden-05.md) | None | Evidence source/reference/metadata syntax and gate regression. |
| HARDEN-006 | [06](2026-10-08-harden-06.md) | 01 | Bounded Git attributes, verified ZIP and historical pilot packaging. |
| HARDEN-007 | [07](2026-10-08-harden-07.md) | 03 | Concrete transfer handoff checks and phase-aware consumers. |
| HARDEN-008 | [08](2026-10-08-harden-08.md) | None | Thin role entries, rule-source audit and Windows diagnostics. |
| HARDEN-009 | [09](2026-10-08-harden-09.md) | 01–08 | Live distinct-model decision pairing on disposable task. |

Prefer 01/02 first, then 03/04/06, then remaining syntax/entry slices and 09.
Within a slice use the task's test cycle and commit boundary. Source inspection
locates functions by name; existing line numbers are not stable across slices.
The full baseline suite had an intermittent dirty-edit failure in review; do
not call the starting tree green or mask that failure with retries.

## Frozen shared interfaces

These are planned interfaces, not claims that they already exist. Consumers use
these names; owners add them without importing CLI mutations into pure checks.

| Owner | Interface | Contract / consumers |
|---|---|---|
| 01 | `review.resolve_commit(root: str, revision: str) -> str` | Literal hex full/short OID only; returns full ancestral commit ID; raises `contracts.ContractError`; no writes. |
| 01 | `review.binding_problems(root: str, ticket_id: str, data: dict, *, allow_rework: bool = False) -> list[str]` | Current recorded pass/changes_requested; pending yields no binding errors; narrow failed-review append exception only when requested. validate, mutate, resume, 03 and 06 consume it. |
| 03 | `workflow_v2.recovery_kind(data: dict) -> str \| None` | `upgrade`, `bootstrap`, `escalation` for coherent unresolved v2 recovery; otherwise None. Existing upgrade flag retained. |
| 03 | `phase_checks.artifact_names(data: dict) -> dict[str, str]` | Existing default artifact names plus configured overrides. |
| 03 | `phase_checks.required_artifacts(phase: str) -> tuple[str, ...]` | One map for existing retained-phase file requirements; no new phases. |
| 03 | `phase_checks.continuation_problems(root: str, ticket_id: str, data: dict, *, require_active: bool = True) -> list[str]` | Checks current retained-phase contracts, no writes. Caller supplies proposed cleared State; permits only valid recorded rework intermediate state. |
| 04 | `upgrade.conversion_problems(data: dict) -> list[str]` | Preflight owned v1 shapes and legal conversion state without mutating; unknown extensions preserved. |
| 05 | `contracts.source_problems(source: str, finding_tag: str) -> list[str]` | Bounded source-family syntax from C5, used by Evidence validator; no source execution or current-file lookup. |
| 06 | `transport.attribute_problems(root: str, paths: list[str]) -> list[str]` | Effective `git check-attr` raw-byte protection notices; no config/index writes. |
| 06 | `artifact_archive.archive_ticket(root: str, ticket_id: str, output: str) -> str` | Validate current v2 bindings and collect raw entries, then export; only requested new output written; raises `ArchiveError`. |
| 06 | `artifact_archive.write_archive(output: str, *, ticket_id: str, snapshot_head: str, entries: dict[str, bytes], bindings: dict[str, str]) -> str` | Safe manifest+ZIP writer; raw hashes agree with every bound entry; used by live export and verified historical packaging. |
| 07 | `contracts.validate_handoff(text: str) -> list[str]` | Section/field readiness syntax, no phase or State mutation; 03 phase checks determine when errors gate. |

`phase_checks` may import contracts, workflow_v2 and review; it must not import
validate or mutate. Keep `validate.reconstruction_problems(root, ticket, data)`
as a delegating compatibility wrapper. 02 changes existing
`review.code_drift(root, ticket_id, reviewed_commit, plan_path)` behavior without
changing its signature. 01 and 02 both touch review.py; land serially.

Bootstrap adds a bounded `recovery.kind: bootstrap` map while preserving unknown
keys. Derive ordinary escalation from existing unresolved escalation fields;
retain `upgrade.requires_reconstruction` for legacy conversions. Cleared flags
must not leave a continuing out-of-phase write permission. Preserve resolution
history and restore only an allowed previous lateral status.

Archive manifest format is JSON `format_version: 1`, `ticket_id`, `snapshot_head`
and `entries`: a list sorted by repository-relative path, each with `path`,
`sha256` and `bound_sha256` (null for unbound supporting files). The ZIP contains
`manifest.json` and the same relative member paths. Bound members include the
registered Plan at its actual source path, not an invented ticket-local copy.
ZIP preserves artifacts, not the Git repository or execution environment.

## Task 1: Integrate independently tested slices and deliver evidence

**Files:**
- Modify: `.scratch/decision-scout-hardening/tickets.md` and per-issue Comments/status only when acceptance evidence exists.
- Modify: `.scratch/decision-scout-hardening/review-disposition.md` evidence status after fixes.
- Read: every child plan's exact source/test write set.

**Interfaces:** Consumes all interfaces above; produces acceptance evidence and a coherent installed workflow, with no new runtime interface.

- [ ] Execute each eligible child plan with its named tests; land overlapping write sets serially.
- [ ] Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts/ai-workflow/tests -p 'test_*.py' -v` once after integration; expected exit 0 and `OK`, with no unresolved dirty-edit failure. A failure requires diagnosis and regression, not repeated runs until green.
- [ ] Review the installed-kit lifecycle and v1 compatibility evidence from that run; expected normal followup, failed review, append, repair, re-review and done still work.
- [ ] Record completed automated slices and remaining live prerequisites in the index; 09 stays pending until its actual sessions and acceptance finish.
- [ ] Commit the integration evidence with exact changed documentation paths; do not claim unresolved manual acceptance complete.

## Self-review record

Coverage: C1→01, C2→02, C3→03, C4→04, C5→05, C6→06 Tasks 1/2,
C7→07, C0/C8→08 and all slice constraints, C9→09. Every review item is owned
in the disposition table. Review Focus cases are attached to the owners' tests.
No dependencies are added solely because of priority or shared files. All
planned interfaces above match their owning child plans. Deferred canonical
hash migration and model dispatch have no implementation tasks by design.

Planning verification: 9 separate issues and 10 plan documents exist; all 87
links in the new documents resolve, dependencies are acyclic, and 9 Python
assertion snippets pass syntax checks. No acceptance boxes are checked. Runtime,
installed Protocol, Skills and adapter bytes match the 63-file pre-planning
snapshot; only documentation was produced. The tracked substantive diff is
limited to parent spec/index updates, with historical comments preserved.
Production tests were not rerun for this documentation-only change.

## Execution handoff

The nine plans are ready for review. No execution method is selected by these
documents. Prefer native execution in dependency order with one independent
whole-change review: shared mutation/validation interfaces make serial integration
useful, while the final live experiment itself requires fresh receiving contexts.
A different execution method may be chosen at implementation handoff. Real pilot
budget remains an explicit prerequisite at that time.
