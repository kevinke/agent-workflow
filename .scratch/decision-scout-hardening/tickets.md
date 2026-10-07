# Decision Scout hardening: Ticket index

Status: ready-for-agent
Parent: [spec](spec.md)
Disposition: [review mapping](review-disposition.md)
Plan: [development plan and shared interfaces](../../docs/superpowers/plans/2026-10-08-scout-hardening.md)

All nine follow-up tickets are unstarted. Original SCOUT-001–008 delivery and pilot history remain separate. Each issue is independently reviewable; the index does not replace its file.

| Ticket | Blocked by | Verifiable outcome |
|---|---|---|
| [01 — Immutable and current Review bindings](issues/01-immutable-current-review.md) | None | A receiver and completion gate agree on the exact immutable change reviewed, for both pass and changes_requested. |
| [02 — Race-safe read-only dirty-code detection](issues/02-race-safe-code-drift.md) | None | Equal-size dirty code cannot retain a Review pass, and the receiving read leaves the real Git index untouched. |
| [03 — Recoverable senior resolution and late-phase bootstrap](issues/03-recoverable-senior-resolution.md) | 01 | A senior can rebuild coherent retained-phase contracts through public commands, then restore the proper continuation without fabricating completed work. |
| [04 — Lossless and malformed-safe explicit upgrade](issues/04-lossless-safe-upgrade.md) | None | Explicit conversion retains extension data and returns an actionable unchanged-input rejection for malformed supported State. |
| [05 — Concrete and traceable Evidence validation](issues/05-traceable-evidence-validation.md) | None | A cheap Scout report accepted by the gate has concrete metadata, usable locators and valid question/fact references. |
| [06 — Durable v2 artifact transport and archives](issues/06-durable-artifact-transport.md) | 01 | Another checkout or an explicit archive preserves the exact v2 bound bytes, including mixed line endings and external Plans. |
| [07 — Phase-aware Handoff readiness](issues/07-phase-aware-handoff.md) | 03 | A model taking over review or completion gets a concrete handoff while early workflow drafts remain usable. |
| [08 — Thin role entries and Windows launch diagnostics](issues/08-thin-roles-windows-runbook.md) | None | Each Harness follows one authoritative rule set, and a Windows policy failure has a bounded documented diagnostic path. |
| [09 — Distinct Scout-to-senior model and Harness pilot](issues/09-paired-model-pilot.md) | 01, 02, 03, 04, 05, 06, 07, 08 | A documented real experiment shows a cheap Scout handing structured facts to a different senior decision model across Harnesses on a bounded nontrivial task. |

## Frontier and suggested order

01, 02, 04, 05 and 08 have no behavioral blockers. Prioritize 01 and 02 because they protect completion. Then 03/04/06, 05/07/08, and finally the live 09 run. 06 consumes 01's shared current-Review checks; 07 consumes 03's shared retained-phase checks. 09 verifies the corrected workflow and therefore consumes all eight predecessors.

Shared files require serial writes or explicit coordination; independence in the table does not authorize parallel writers. No Work Packet workflow is enabled by this index. Each plan can be executed in a fresh context with the parent spec and shared-interface plan.

09's documentation is ready; its live execution additionally requires available models/Harnesses and a new explicit session budget. Budget is an execution prerequisite, not an invented ticket dependency or an assumed extension of SCOUT-008.

## Comments

- 2026-10-08 — Nine outcome slices prepared from the review. Statuses describe the new work only; no production fixes or live sessions occurred while producing these documents.
