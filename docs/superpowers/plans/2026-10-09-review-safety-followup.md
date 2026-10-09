# Review Safety Follow-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the three 2026-10-09 follow-up tickets without rewriting completed hardening work or publishing unisolated reviewer evidence.

**Architecture:** Execute 010 before 011 because guarded publication depends on trustworthy live drift checks. Close 012's narrow already-verified template delivery separately, and retain 009 as pending real-session acceptance with its new safety prerequisites.

**Tech Stack:** Python 3 stdlib, Git, unittest; optional installed Linux bubblewrap for the explicit 011 profile.

**Spec:** [supplemental spec C2/C10/C11](../../../.scratch/decision-scout-hardening/spec.md), [ticket index](../../../.scratch/decision-scout-hardening/tickets.md).

## Global Constraints

- Keep `workflow_version: 2`, `schema_version: 1`, Python 3 stdlib only and the existing restricted YAML parser.
- Keep v1 Ticket behavior and historical pilot completion unchanged.
- Keep v2 SHA-256 over original artifact bytes; do not normalize line endings before hashing.
- Protocol and artifact contracts own semantic rules; Skills and adapters point to them.
- Structural validation establishes conformance, not the truth of natural-language claims or model seniority.

Use the per-ticket plans below as the task contracts; this document adds sequence only, not duplicate implementation tasks. One writer at a time for shared Review/protocol files. No automatic Work Packet mode, global permissions/config edits, new model allocation or historical artifact normalization.

## Review Focus

- Index hints plus cached-mtime collision: 010 Task 1.
- Missing sparse paths and copied-index failures: 010 Task 1.
- Snapshot creation without real whole-process denial: 011 Tasks 1/2.
- Live-input drift or interruption before publication: 011 Task 3.
- Broad CRLF normalization or staging unrelated files: 012 Task 1.

---

## Execution sequence and exact boundaries

| Ticket | Development plan | Write boundary | Completion evidence |
| --- | --- | --- | --- |
| HARDEN-010 | [index-independent currentness](2026-10-09-harden-10.md) | Existing drift helper, three test modules, two authoritative contracts | Public flag/racy/sparse/read-only cases, all consumers, full suite/v1 |
| HARDEN-011 | [isolated review/publication](2026-10-09-harden-11.md) | Three bounded new modules; CLI/candidate parser; tests; source-of-truth docs and thin adapters | Actual supported-host denial, provenance/currentness/recovery, installed lifecycle |
| HARDEN-012 | [LF delivery closure](2026-10-09-harden-12.md) | Root attributes and existing template only; evidence records after acceptance | Scoped committed OID and six fresh checkout/install results |

- [ ] Review the per-ticket plans and select execution method before implementation. The current request saves plans only; there is no runtime, registration, model-session or publication claim.
- [ ] Prepare an isolated implementation checkout at execution time; carry over 012's exact LF rule and required semantic spec changes deliberately. Do not copy/stage every pre-existing CRLF-only change. Establish a tested baseline once.
- [ ] Execute 010's two tasks serially and capture their actual regression/integration evidence.
- [ ] Execute 011's four tasks serially against 010; unsupported Harness/host boundaries stay blocked. All reviewer probes use a restricted snapshot.
- [ ] Execute 012's single delivery task when commit is authorized; use its existing local verification instead of inventing another implementation round.
- [ ] Reassess 009 launch only after 010/011 acceptance, a demonstrated boundary for the selected actual Harness and a separately authorized available session budget. Preserve the original pilot task, historical results and exhausted allocation.

## Shared interfaces and handoff

010 retains `review.code_drift(root, ticket_id, reviewed_commit, plan_path) -> list[str]`, exact four record exemptions and read-only real-index behavior. 011 consumes this interface in preparation and publication; its exact new APIs and guarded `set-review` options are frozen in its own plan. Historical raw `set-review` reports retain their original semantics and acquire no invented isolation attestation.

012 has no new runtime interface: exact template/installed bytes are `b"** -text\n"`. Its attribute rule is a verification prerequisite for fresh implementation checkouts; publication can be independent of 010/011.

After planning, these local issue documents are **planned**, not registered `.ai/work` execution contracts. At execution, use the repo's existing adoption/registration lifecycle when applicable rather than treating these prose plans as registered state.

## Self-review record

Each new Ticket has one linked plan with file ownership, frozen interfaces, test assertions/commands, error/compatibility limits and bounded commits. 009's launch prerequisites are amended without claiming new live acceptance. No runtime files or historical bound artifacts are changed by this planning step.
