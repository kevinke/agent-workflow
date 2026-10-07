# 06: Durable v2 artifact transport and archives

Ticket ID: HARDEN-006
Type: task
Status: ready-for-agent
Blocked by: 01
Parent: [supplemental spec](../spec.md#c6--durable-raw-byte-transport-harden-006)
Source findings: S-05; CRLF pilot observation; [disposition](../review-disposition.md)
Plan: [development plan](../../../docs/superpowers/plans/2026-10-08-harden-06.md)

## What to build

Another checkout or an explicit archive preserves the exact v2 bound bytes, including mixed line endings and external Plans.

## Scope and ownership

Own the complete C6 outcome from contract/documentation through public-command behavior and its regression or manual evidence. Exact files and interfaces are frozen in the linked plan. Honor its write set; other work may share mutation/validation files, so do not revert unrelated changes and schedule one writer for overlapping files. This issue is pending implementation; original SCOUT tickets stay historical.

## Acceptance criteria

- [ ] New work directories get bounded raw-byte Git attributes; existing user attributes are preserved and conflicts produce read-only warnings.
- [ ] Referenced external Plans have documented explicit per-path protection; no global Git configuration or hash-algorithm change.
- [ ] Explicit archive-artifacts exports original bytes plus manifest only after current Evidence/Audit/Plan/Review identity checks.
- [ ] Stale bindings, path escapes, duplicate members, existing output and write failure reject without source/State changes or partial output.
- [ ] Fresh clone/checkout under autocrlf true/false and ZIP extraction preserve every recorded binding.
- [ ] Existing pilot bound bytes are packaged and verified after fresh clone without changing historical State or re-gating; unavailable originals are reported honestly.

## Verification

Use the linked plan's named cases and commands. Negative mutations preserve State bytes; read-only operations preserve artifacts and Git index. HARDEN-009 has manual live acceptance and is not completed by automated fixtures. Global compatibility constraints in the supplemental spec apply to every slice.

## Escalation conditions

If implementation requires changing v2 digest semantics, completed task history, acceptance boundaries or dependencies beyond the linked contract, record the conflict before proceeding. Do not silently widen the slice or infer model-session budget from this planning request.

## Comments

- 2026-10-08 — Created from the post-implementation review at the user's request; ready for development planning/execution, not a resolved finding.
