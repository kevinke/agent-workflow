# 09: Distinct Scout-to-senior model and Harness pilot

Ticket ID: HARDEN-009
Type: task
Status: open; live pilot stopped at Scout permission failure (2026-10-10)
Blocked by: 01, 02, 03, 04, 05, 06, 07, 08, 10, 11
Parent: [supplemental spec](../spec.md#c9--distinct-model-paired-pilot-harden-009)
Source findings: O1: actual model pairing gap; [disposition](../review-disposition.md)
Plan: [development plan](../../../docs/superpowers/plans/2026-10-08-harden-09.md)

## What to build

A documented real experiment shows a cheap Scout handing structured facts to a different senior decision model across Harnesses on a bounded nontrivial task.

## Scope and ownership

Own the complete C9 outcome from contract/documentation through public-command behavior and its regression or manual evidence. Exact files and interfaces are frozen in the linked plan. Honor its write set; other work may share mutation/validation files, so do not revert unrelated changes and schedule one writer for overlapping files. This issue is pending implementation; original SCOUT tickets stay historical.

## Additional launch prerequisites (2026-10-09)

Close [10](10-index-flag-independent-review.md) and
[11](11-isolated-reviewer-publication.md) before launching the pilot. The original
plan retains its experimental scope; add the corrected currentness/isolation
prerequisites before execution. This is a launch dependency update, not a new
session authorization, budget increase or change to historical pilot acceptance.

## Acceptance criteria

- [ ] Prepare a disposable task with frozen behavior/DQs, exact receiving inputs, session cap and stop criteria before launch.
- [ ] Actual Scout and senior decision model identities differ; at least one Scout-to-decision transfer crosses Harnesses into fresh context with resume first.
- [ ] Independent review has fresh context and uses persisted artifacts; behavior acceptance and both identity/traceability checks are recorded.
- [ ] Record targeted rereads versus repeated broad exploration, rework, artifact changes and telemetry provenance; missing measurements stay UNKNOWN.
- [ ] A live run needs newly authorized available budget; original SCOUT-008 completion and its exhausted allocation remain unchanged.
- [ ] Publish actual outcome/logs even on failure; acceptance checkboxes close only from live evidence, not simulated CLI runs or a prepared runbook.

## Verification

Use the linked plan's named cases and commands. Negative mutations preserve State bytes; read-only operations preserve artifacts and Git index. HARDEN-009 has manual live acceptance and is not completed by automated fixtures. Global compatibility constraints in the supplemental spec apply to every slice.

## Escalation conditions

If implementation requires changing v2 digest semantics, completed task history, acceptance boundaries or dependencies beyond the linked contract, record the conflict before proceeding. Do not silently widen the slice or infer model-session budget from this planning request.

## Comments

- 2026-10-08 — Created from the post-implementation review at the user's request; ready for development planning/execution, not a resolved finding.

- 2026-10-09 — Added 10/11 as safety prerequisites for the actual live run.
  No sessions launched and no budget inferred from this documentation request.

- 2026-10-10 — Actual preparation and diagnostics are on `codex/harden-009-pilot`:
  Qoder CLI installed and authenticated; exact account/runtime model is
  Qwen3.8-Flash. The user authorized six counted attempts, existing quota only.
  Two Codex CLI isolation diagnostics were counted (first missing a runtime
  companion, second observed shell EROFS and file-tool policy denial with host
  recheck). The third, actual Scout session resumed first but its required
  Evidence write was permission-denied; it was stopped without a senior handoff.
  Candidate and failures are retained in [pilot/report.md](../pilot/report.md).
  HARDEN-009 is not accepted; no live Review, implementation or archive exists.
