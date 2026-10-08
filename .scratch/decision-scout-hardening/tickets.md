# Decision Scout hardening: Ticket index

Status: integration recorded 2026-10-09; HARDEN-009 pending its live run
Parent: [spec](spec.md)
Disposition: [review mapping](review-disposition.md)
Plan: [development plan and shared interfaces](../../docs/superpowers/plans/2026-10-08-scout-hardening.md)

Tickets 01–08 are implemented and independently reviewed on branch
`decision-scout-hardening`; acceptance evidence is recorded in each issue and in
the [disposition](review-disposition.md). 02 carries one open integration
caveat: its racy done/resume regression failed in test-fixture setup on the
Windows host (diagnosed 2026-10-09; production drift detection passed). 09 is
not started and stays pending until its live prerequisites are met. Original
SCOUT-001–008 delivery and pilot history remain separate. Each issue is
independently reviewable; the index does not replace its file.

| Ticket | Blocked by | Status | Verifiable outcome |
|---|---|---|---|
| [01 — Immutable and current Review bindings](issues/01-immutable-current-review.md) | None | Complete (automated) | A receiver and completion gate agree on the exact immutable change reviewed, for both pass and changes_requested. |
| [02 — Race-safe read-only dirty-code detection](issues/02-race-safe-code-drift.md) | None | Implemented; one racy fixture test awaits a rerun-of-record | Equal-size dirty code cannot retain a Review pass, and the receiving read leaves the real Git index untouched. |
| [03 — Recoverable senior resolution and late-phase bootstrap](issues/03-recoverable-senior-resolution.md) | 01 | Complete (automated) | A senior can rebuild coherent retained-phase contracts through public commands, then restore the proper continuation without fabricating completed work. |
| [04 — Lossless and malformed-safe explicit upgrade](issues/04-lossless-safe-upgrade.md) | None | Complete (automated) | Explicit conversion retains extension data and returns an actionable unchanged-input rejection for malformed supported State. |
| [05 — Concrete and traceable Evidence validation](issues/05-traceable-evidence-validation.md) | None | Complete (automated) | A cheap Scout report accepted by the gate has concrete metadata, usable locators and valid question/fact references. |
| [06 — Durable v2 artifact transport and archives](issues/06-durable-artifact-transport.md) | 01 | Complete (automated) | Another checkout or an explicit archive preserves the exact v2 bound bytes, including mixed line endings and external Plans. |
| [07 — Phase-aware Handoff readiness](issues/07-phase-aware-handoff.md) | 03 | Complete (automated) | A model taking over review or completion gets a concrete handoff while early workflow drafts remain usable. |
| [08 — Thin role entries and Windows launch diagnostics](issues/08-thin-roles-windows-runbook.md) | None | Complete (automated) | Each Harness follows one authoritative rule set, and a Windows policy failure has a bounded documented diagnostic path. |
| [09 — Distinct Scout-to-senior model and Harness pilot](issues/09-paired-model-pilot.md) | 01, 02, 03, 04, 05, 06, 07, 08 | Pending live run (budget prerequisite) | A documented real experiment shows a cheap Scout handing structured facts to a different senior decision model across Harnesses on a bounded nontrivial task. |

## Frontier and suggested order

01, 02, 04, 05 and 08 have no behavioral blockers. Prioritize 01 and 02 because they protect completion. Then 03/04/06, 05/07/08, and finally the live 09 run. 06 consumes 01's shared current-Review checks; 07 consumes 03's shared retained-phase checks. 09 verifies the corrected workflow and therefore consumes all eight predecessors.

Shared files require serial writes or explicit coordination; independence in the table does not authorize parallel writers. No Work Packet workflow is enabled by this index. Each plan can be executed in a fresh context with the parent spec and shared-interface plan.

09's documentation is ready; its live execution additionally requires available models/Harnesses and a new explicit session budget. Budget is an execution prerequisite, not an invented ticket dependency or an assumed extension of SCOUT-008.

## Comments

- 2026-10-08 — Nine outcome slices prepared from the review. Statuses describe the new work only; no production fixes or live sessions occurred while producing these documents.
- 2026-10-09 — Integration: 01–08 implemented on `decision-scout-hardening` (01: 0f1f2b5, 477e65c; 02: 8a0b92b; 03: 235bc88, 256b312, fba580a, bf9b016; 04: d822833, b76f51f; 05: 46d50c0; 06: 793ac20, 3014423, 9ee8a4f, cebc72; 07: 924a580; 08: 3cef3db), each slice independently reviewed. Full-suite integration run at 3cef3db (`PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s scripts/ai-workflow/tests -p 'test_*.py' -v`): 399 tests, 397 passed, 2 pre-existing symlink skips, 1 failure — HARDEN-002's `test_racy_edit_blocks_done_and_resume` failed in fixture setup (Windows cross-process mtime-visibility race in the test fixture; production drift detection passed every other racy case). Diagnosed, not retried. 09 has no live run: it requires available models/Harnesses and a newly authorized session budget, so it stays pending.
