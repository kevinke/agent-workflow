# Decision Scout hardening: Ticket index

Status: historical 01–08 complete; 10 integrated (cc9be8f); 11 integrated (cba2497,
488 tests `OK (skipped=4)` on the merged result); 12 published and
fresh-checkout verified; 09 complete; actual paired pilot accepted (2026-10-10)
Parent: [spec](spec.md)
Disposition: [review mapping](review-disposition.md)
Plan: [development plan and shared interfaces](../../docs/superpowers/plans/2026-10-08-scout-hardening.md)

Tickets 01–08 are implemented and independently reviewed on branch
`decision-scout-hardening`; acceptance evidence is recorded in each issue and in
the [disposition](review-disposition.md), backed by the green full-suite run of
record at 483a423 (399 tests, `OK (skipped=2)`). 09 completed an actual
Qoder/Qwen3.8-Flash → fresh Codex/gpt-5.6-sol handoff, five behavior cases,
isolated independent Review and verified export. All eight pilot starts,
including failures, remain in the [pilot report](pilot/report.md); the separate
final branch review is counted as startup nine. Original
SCOUT-001–008 delivery and pilot history remain separate. Each issue is
independently reviewable; the index does not replace its file.

| Ticket | Blocked by | Status | Verifiable outcome |
|---|---|---|---|
| [01 — Immutable and current Review bindings](issues/01-immutable-current-review.md) | None | Complete (automated) | A receiver and completion gate agree on the exact immutable change reviewed, for both pass and changes_requested. |
| [02 — Race-safe read-only dirty-code detection](issues/02-race-safe-code-drift.md) | None | Complete (automated) | Equal-size dirty code cannot retain a Review pass, and the receiving read leaves the real Git index untouched. |
| [03 — Recoverable senior resolution and late-phase bootstrap](issues/03-recoverable-senior-resolution.md) | 01 | Complete (automated) | A senior can rebuild coherent retained-phase contracts through public commands, then restore the proper continuation without fabricating completed work. |
| [04 — Lossless and malformed-safe explicit upgrade](issues/04-lossless-safe-upgrade.md) | None | Complete (automated) | Explicit conversion retains extension data and returns an actionable unchanged-input rejection for malformed supported State. |
| [05 — Concrete and traceable Evidence validation](issues/05-traceable-evidence-validation.md) | None | Complete (automated) | A cheap Scout report accepted by the gate has concrete metadata, usable locators and valid question/fact references. |
| [06 — Durable v2 artifact transport and archives](issues/06-durable-artifact-transport.md) | 01 | Complete (automated) | Another checkout or an explicit archive preserves the exact v2 bound bytes, including mixed line endings and external Plans. |
| [07 — Phase-aware Handoff readiness](issues/07-phase-aware-handoff.md) | 03 | Complete (automated) | A model taking over review or completion gets a concrete handoff while early workflow drafts remain usable. |
| [08 — Thin role entries and Windows launch diagnostics](issues/08-thin-roles-windows-runbook.md) | None | Complete (automated) | Each Harness follows one authoritative rule set, and a Windows policy failure has a bounded documented diagnostic path. |
| [09 — Distinct Scout-to-senior model and Harness pilot](issues/09-paired-model-pilot.md) | 01, 02, 03, 04, 05, 06, 07, 08, 10, 11 | Done | Actual Qoder/Qwen3.8-Flash → fresh Codex/gpt-5.6-sol transfer, isolated independent pass, five behavior cases and verified export; failures/limits retained in pilot report. |
| [10 — Review drift independent of index hints](issues/10-index-flag-independent-review.md) | None | Complete (automated); integrated at cc9be8f | Flagged dirty/deleted code cannot obtain or retain either Review verdict; real index and racy-stat detection are preserved. |
| [11 — Isolated reviewer verification and publication](issues/11-isolated-reviewer-publication.md) | 10 | Complete (automated + real-host boundary); integrated at cba2497 | Verifier writes stay inside a restricted snapshot; only a current, identified review is published to live workflow records. |
| [12 — LF-stable installer template](issues/12-lf-stable-installer-template.md) | None | Published (86a823c); fresh-checkout verified | The protection template and installed output remain LF across six checkout scenarios; 400 tests pass. |

## Current follow-up frontier (2026-10-10)

The [follow-up master plan](../../docs/superpowers/plans/2026-10-09-review-safety-followup.md)
and per-ticket [10](../../docs/superpowers/plans/2026-10-09-harden-10.md),
[11](../../docs/superpowers/plans/2026-10-09-harden-11.md),
[12](../../docs/superpowers/plans/2026-10-09-harden-12.md) plans record the
completed safety prerequisites. These development plans are not registered
execution contracts.
Shared Review/protocol files require serial writes. 12 is published at 86a823c
with its six-case matrix and fresh-checkout verification recorded; it needs no
further implementation round, and the LF attribute rule it supplies was
published before HARDEN-010's integration run, as that run required.

10 and 11 are integrated, and 09 used a newly authorized budget, extended
explicitly by the user while retaining the failed starts. PAIR-01 reached
`done` with a current `pass` Review and verified export on 2026-10-10. The 009
delivery was fast-forwarded into `master` at `465336c` after the user chose
local integration and direct push to `origin/master`, without a PR. The original 01–08 acceptance
stays historical and does not claim these new follow-ups were tested. The
earlier frontier below records the original delivery order rather than today's
outstanding work.

## Original frontier and suggested order (historical, superseded)

01, 02, 04, 05 and 08 have no behavioral blockers. Prioritize 01 and 02 because they protect completion. Then 03/04/06, 05/07/08, and finally the live 09 run (now also gated by 10/11 above). 06 consumes 01's shared current-Review checks; 07 consumes 03's shared retained-phase checks. 09 verifies the corrected workflow and originally consumed all eight predecessors; its new safety prerequisites are recorded above.

Shared files require serial writes or explicit coordination; independence in the table does not authorize parallel writers. No Work Packet workflow is enabled by this index. Each plan can be executed in a fresh context with the parent spec and shared-interface plan.

At that original frontier, 09's documentation was ready; its live execution
required available models/Harnesses and a new explicit session budget. Budget
was an execution prerequisite, not an invented ticket dependency or an assumed
extension of SCOUT-008. The accepted 2026-10-10 result above supersedes this
historical launch frontier.

## Comments

- 2026-10-08 — Nine outcome slices prepared from the review. Statuses describe the new work only; no production fixes or live sessions occurred while producing these documents.
- 2026-10-09 — Integration: 01–08 implemented on `decision-scout-hardening` (01: 0f1f2b5, 477e65c; 02: 8a0b92b; 03: 235bc88, 256b312, fba580a, bf9b016; 04: d822833, b76f51f; 05: 46d50c0; 06: 793ac20, 3014423, 9ee8a4f, cebc72; 07: 924a580; 08: 3cef3db), each slice independently reviewed. Full-suite integration run at 3cef3db (`PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s scripts/ai-workflow/tests -p 'test_*.py' -v`): 399 tests, 397 passed, 2 pre-existing symlink skips, 1 failure — HARDEN-002's `test_racy_edit_blocks_done_and_resume` failed in fixture setup (Windows cross-process mtime-visibility race in the test fixture; production drift detection passed every other racy case). Diagnosed, not retried. 09 has no live run: it requires available models/Harnesses and a newly authorized session budget, so it stays pending.
- 2026-10-09 — Green run of record: after fixture hardening 483a423 (`test_review_v2.py` only; scoped re-review passed), the same full-suite command at 483a423 finished `Ran 399 tests in 372.617s` — `OK (skipped=2)`, exit 0; the only skips remain the two pre-existing symlink-privilege cases. `ReviewV2Test.test_racy_edit_blocks_done_and_resume` passed, closing 02's caveat; all eight automated slices are complete with checked acceptance evidence. 09 is unchanged: no live run and no authorized session budget.

- 2026-10-09 — Created 10/11 for newly identified index hints and verifier isolation;
  both await planning, with 11 depending on 10. Recorded locally verified LF fix
  as 12 (not yet committed). 09 now waits for 10/11 and its existing live budget;
  completed 01–08 and their historical plans/evidence were not reopened.

- 2026-10-09 — Added development plans for 10/11 and delivery closure for 12,
  plus a follow-up sequence. Planned status does not claim implementation.
  009 launch prerequisites are updated; no new model budget is allocated.

- 2026-10-09 — Published 12 as 86a823c (`fix: keep installer protection template
  LF across checkouts`), staging only root `.gitattributes`; the template already
  matched HEAD so it produced no diff. Six-case LF/CRLF × autocrlf matrix rerun
  against that committed revision passed 6/6 (template, committed blob and real
  `init.init` output all `b"** -text\n"`, custom target attributes preserved),
  with a negative control at pre-fix 3a4a980 showing `b"** -text\r\n"` under
  `autocrlf=true`. Fresh `--no-local` checkout of 86a823c ran
  `test_init test_transport`: 17 tests, OK, exit 0. 12's publication acceptance
  is closed. 10 remains unimplemented: `review.py` is untouched and its new
  tests exist only in the `harden-010` worktree, where the added block is
  duplicated and the fix is absent. (State as of that entry; superseded by the
  next one.)

- 2026-10-09 — Implemented, independently reviewed and integrated 10 on branch
  `harden-010` (Task 1 376e4b6, Task 2 487adb7, task fix round 4830255,
  whole-branch fix wave 48e2051, corrections a542486, evidence cc9be8f),
  fast-forwarded into `master` at cc9be8f. `review.py` now assesses drift
  against a disposable `GIT_INDEX_FILE` copy whose `assume-unchanged` and
  `skip-worktree` bits are cleared and whose mtimes are restored so racy-stat
  detection still applies; flagged edits, deletes and unusual paths can no
  longer exempt themselves from either verdict, unmerged entries are assessed
  instead of raising, and the probe creates nothing in the real Git directory.
  The five public consumers (`set-review`, `validate`, `resume`,
  `advance --to done`, `archive-artifacts`) share that one `code_drift`
  assessment. Full-suite run of record on the merged tree at cc9be8f:
  `Ran 420 tests in 455.868s` — `OK (skipped=2)`, exit 0, the skips still the
  two pre-existing symlink-privilege cases; identical counts to the pre-merge
  run on the same commit. Worktree removed and branch deleted. 11 is unblocked.
  Surfaced as non-blocking follow-ups, not fixed here: the `.gitignore`
  concatenation at 3a4a980 leaves neither `.superpowers/` nor `.worktrees/`
  ignored, `git status`'s Repository row in `resume` is still hint-blind, and
  `core.fsmonitor` (same defect family, unset in this repo) is out of 10's
  scope.
