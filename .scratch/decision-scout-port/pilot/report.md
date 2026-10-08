# Pilot Report — Measured Live Model/Harness Handoff (SCOUT-008)

Status: **COMPLETE — both pilot tickets (`PILOT-BUG-01`, `PILOT-FEAT-01`) reached
`done` through real live sessions, including persisted cross-Harness handoffs
(Harness A → Harness B) with clean receiver contexts.**
Date: 2026-10-07. Consent: **yes** (external model quota spend authorised; the cap
was raised from 5 sessions/≈3 min to 10 sessions/≤5 min for the completion run).
Sessions consumed: **15** (5/5 of the first cap + 10/10 of the raised cap).

Procedure: [runbook.md](runbook.md). Plan Task 2, spec Testing Decisions, issue
[08-live-model-harness-pilot.md](../issues/08-live-model-harness-pilot.md).
Disposable target: `%TEMP%\scout008-target` (git repo; two isolated branches,
common root `2fee994`). Raw Harness-B logs and byte-recovery helpers:
[pilot/logs/](logs/). Archived ticket artifacts: [pilot/bug/](bug/),
[pilot/feature/](feature/) — every archived file was restored to the exact byte
form bound in that ticket's `state.yaml` (sha256 verified).

## Consent and budget

- First authorisation: **at most 5 sessions, ~3 min each**, option A
  (Harness A = Trae session/subagents; Harness B = `codex` CLI). Consumed
  **5/5**: scout (1), senior (1), three policy-blocked codex attempts (3).
- Raised authorisation: **10 sessions, up to 5 min each**. Consumed **10/10**:
  sandbox-policy probes (4), Harness-A bug executor (1), codex bug review v1
  [blocked] (1), codex bug review v2 [pass] (1), Harness-A feature executor (1),
  codex feature review [changes_requested] (1), codex feature re-review [pass]
  (1). The post-#9 handoff rework round was completed in the Harness-A context
  (staging + workflow CLI); it has no separate session log (UNKNOWN).
- Measurable usage: tokens reported by codex:
  36,273 + 52,813 + 51,401 + 65,395 = **205,882** (only 4 of 15 sessions expose
  usage). Trae-side tokens/cost, probe details, and all blocked attempts:
  **UNKNOWN**. No provider pricing is assumed; no savings percentage is claimed.

## What happened (Task 2, Steps 1–2)

Two long-lived branches in the disposable target, one Ticket each (no
interference; merge-base = the shared root commit). The full lifecycle ran end
to end: scout → audit/decision/Plan → executor → independent review → (one
rework loop on the feature) → `done`, with `validate` OK recorded at every
review.

**Bug `PILOT-BUG-01` (branch `pilot/bug`, head `a1cbdab`).** Scout evidence
(`0504a25`, observed commit `b5a13a8`, F-01..F-04 / DQ-01..03 answered); senior
audit/decision/Plan (`a947051`); gate re-attested to worktree bytes
(`a8e7f0b`/`bc290ef`); Harness-A executor fixed `read()` (`4a92d74`, demo green);
Harness-B independent review `pass` (`bdc4477`, reviewed `4a92d74`, plan
`67a62c31…`); `done` (`a1cbdab`).

**Feature `PILOT-FEAT-01` (branch `pilot/feat`, head `aea68a6`).** Scout evidence
(`d5234df`, observed commit `0a98f42`, F-01..F-05 / DQ-01..03 answered); senior
`b856779`; gate re-attest `193cf8f`; executor added `CachedValue.reload`
(`da08060`); Harness-B review v1 `changes_requested` (`851a7bd`) — sole finding:
the persisted handoff was still an unfilled template; rework task appended
(`5e39a5d`) and completed (`72a3a21`); fresh Harness-B re-review `pass`
(`09580e6`, reviewed `98a2720`, plan `349913c6…`); `done` (`aea68a6`).

Commit chains (both from root `2fee994`) are listed verbatim in each ticket's
archived `handoff.md`/`progress.md` and in [pilot/logs/](logs/).

## Cross-Harness handoff (the required A → B crossing)

The handoff that crossed two actual Harnesses happened at the **review**
boundaries; the *planned* scout→senior crossing was not used because the senior
ran on Harness A in this pilot (recorded honestly in [runbook.md](runbook.md) §8).

- The receiver in every crossing was a **fresh `codex exec` process** (Harness B)
  with a self-contained prompt: repo, Ticket id, `resume` command, referenced
  artifacts, and expected hashes — **never the sender's conversation**. Each
  receiver's first action was `ai-workflow resume <ticket>`; each reported the
  resume result (phase, gate freshness, next role) in its Review's "Session log".
- Bug handoff: A → B, session `01a116af-04e7-7470-9716-b6d1b03323bb`
  ([log](logs/codex-review-bug-v2-out.txt)); 32 commands; verdict `pass`.
- Feature handoff: A → B, session `01a116b7-b5ea-7282-a914-93ab4ee6d74c`
  ([log](logs/codex-review-feat-out.txt)); 23 commands; verdict
  `changes_requested` (handoff placeholder). After the recorded rework, a second
  fresh B context `01a116cb-90b0-7d51-beb4-4661625912e6`
  ([log](logs/codex-rereview-feat-out.txt)); 31 commands; verdict `pass`.
- The reviewers' only inputs were persisted artifacts and the prompt; the one
  earlier receiver-side reread (truncated `ROLES.md`/`ARTIFACTS.md`) was a
  targeted reread, not repeated exploration.

## The Harness-B policy block and its resolution

The first three codex attempts (chain-budget phase) and the first full receiver
session [#7] were **blocked before any useful work**: every submitted shell
invocation returned
`CreateProcess … rejected: blocked by policy` (39 rejected invocation lines in
[the v1 console log](logs/codex-review-bug-console.txt); verdict
`changes_requested`/inconclusive because verification was impossible; metadata
values `null`; not persisted). The working fix, found by probing sandbox launch
options, is to launch codex with:

```
-c windows.sandbox="unelevated"
```

After that, all logged receiver commands ran: 86 commands across sessions
[#8](logs/codex-review-bug-v2-console.txt), [#9](logs/codex-review-feat-console.txt),
[#10](logs/codex-rereview-feat-console.txt), with no policy rejection and no
unresolved verification gap (one auxiliary skill lookup in #9 failed on a wrong
path and was recovered). The session-policy banner still reports the sandbox as
`read-only`; the flag changes the Windows sandbox execution mode, not the
read-only posture. The four policy probes kept no logs — their details are
**UNKNOWN**; the observable before/after evidence is #7 vs #8–#10.

## Byte-level gate friction (observed; left for a separate follow-up)

The v2 evidence gate binds `evidence-audit.md` bytes exactly, while the host's
`core.autocrlf=true` rewrites line endings on branch switches. During the pilot
this made the recorded gate stale and forced `set-gate` **re-attestation** three
times (`a8e7f0b`/`bc290ef` for the bug; `193cf8f` for the feature). The same
byte-sensitivity affected archiving: the two `evidence-audit.md` files no longer
existed in their bound byte forms (pure CRLF worktree rewrites vs the bound
mixed line-ending masks), so both were **recovered byte-exactly** (search over
k-segment masks; see [recover_audit_bytes.py](logs/recover_audit_bytes.py)) and
all archived artifacts were verified against the `state.yaml` bindings. Note: a
fresh checkout of the archive can re-normalize line endings, so byte-level
verification must use the archived worktree as committed.

## Anchor audit (plan Task 2 Step 3 — completed)

Independently re-checked against the actual repositories (no writes to the
target; extracted copies for runtime reproduction):

- Evidence snapshot (`b5a13a8:service.py`, same pristine fixture for the
  feature's `0a98f42`): class `CachedValue` (L1), `__init__` (L2–3) with
  `self._value = config["value"]` (L3), `read` (L5–6) returning `self._value` —
  matches F-01/F-02/F-03 anchors as written; `demo.py` anchors (import L1,
  construction L6, mutation L8, reads L7/L10) match F-04.
- Final bug code (`a1cbdab:service.py`): `self._config = config` and
  `return self._config["value"]`; task commit `4a92d74` touches only `service.py`
  plus the ticket's own artifacts; `demo.py` unchanged across `b5a13a8..a1cbdab`.
- Runtime re-run (fresh, in extracted copies): bug `python demo.py` →
  `initial=1` / `configured=2` / `actual=2`, exit 0; bug `test_bug` (runbook §3,
  run against the fixed copy) → OK 1 test; feature `test_reload` (runbook §4) →
  OK 2 tests; feature inline acceptance commands on the live worktree → `5` and
  `7`, exit 0, worktree still clean. Every run matched its declared expectation.
- Negative-search scope: as declared (target-root `*.py` only, vendored
  `.ai/workflow/examples/scout-fixture/` excluded). **No wrong or missing anchor
  was found in either evidence report.** The independent reviewer sessions
  reached the same conclusions in their own re-runs.

## Session records

Harness A sessions (Trae; the model label is the session label; token/tool
telemetry is not exposed — UNKNOWN):

| Task | Role | Model | Harness | Window (+0800) | Usage | Output artifacts | Repeated exploration | Targeted verification | Outcome |
|---|---|---|---|---|---|---|---|---|---|
| both | scout (cheap) | DeepSeek-V4.1-Flash | A (Trae) | 20:06 → 20:13 | UNKNOWN | `bug/evidence.md` (`0504a25`), `feature/evidence.md` (`d5234df`) | none observed | runtime repro (`python demo.py` before-state) | decision-ready evidence, no critical UNKNOWN |
| both | senior: audit → decision → plan | DeepSeek-V4.1-Flash | A (Trae) | 20:14 → 20:44 | UNKNOWN | `*/evidence-audit.md`, `*/decision.md`, `*/plan.md` (`a947051`, `b856779`, re-attest `a8e7f0b`/`bc290ef`, `193cf8f`) | none observed | pivotal-anchor re-check | gate `sufficient` round 1; Plans registered |
| PILOT-BUG-01 | executor (task 1) | DeepSeek-V4.1-Flash | A (Trae subagent; claim 13:51:35Z) | ~21:51 → 21:55 | UNKNOWN | `service.py` fix + `progress.md`/`handoff.md` (`4a92d74`, boundary `a50a955`) | none | `python demo.py` green | task 1 complete, no deviation |
| PILOT-FEAT-01 | executor (task 1) | DeepSeek-V4.1-Flash | A (Trae subagent; claim 14:13:24Z) | ~22:13 → 22:14 | UNKNOWN | `service.py` + `progress.md` (`da08060`, boundary `f06cec2`) | none | inline acceptance green | task 1 complete; handoff left unfilled → caught by review |
| PILOT-FEAT-01 | handoff rework (task 2) | (Harness-A context) | A (Trae) | 22:28 → 22:35 | UNKNOWN | `plan.md` append (`5e39a5d`), `handoff.md`/`progress.md`/`state.yaml` (`72a3a21`, boundary `98a2720`) | none | placeholder probe + acceptance re-runs + `validate` OK | handoff completed; re-review then passed |

Harness B sessions (`codex-cli 0.160.0`, model `gpt-6.1-sol` observed at run
time; all read-only, launched with `-c windows.sandbox="unelevated"`):

| # | Task | Role | Session id | Window (+0800) | Usage | Tool activity | Output artifacts | Repeated exploration | Targeted verification | Outcome |
|---|---|---|---|---|---|---|---|---|---|---|
| — | both | receiver attempts ×3 (pre-fix) | (not retained) | before 21:20 | UNKNOWN | UNKNOWN | none | — | — | **blocked by session policy** |
| — | — | sandbox-policy probes ×4 | (not retained) | 21:20 → 22:05 | UNKNOWN | UNKNOWN | none | — | — | found `windows.sandbox="unelevated"` |
| 7 | PILOT-BUG-01 | reviewer v1 | `01a116a7-bfef-7ef0-bb5a-d29db7da23f7` | 21:57:34 → 21:59:19 | 36,273 tokens | all invocations policy-rejected (39 lines) | `codex-review-bug-out.txt` (not persisted) | — | impossible (blocked) | `changes_requested`/inconclusive; superseded by #8 |
| 8 | PILOT-BUG-01 | reviewer v2 | `01a116af-04e7-7470-9716-b6d1b03323bb` | 22:05:31 → 22:09:20 | 52,813 tokens | 32 commands, all green | `bug/review.md` (`bdc4477`, sha `1421855e…`), logs | none | re-ran demo; hashes vs bindings; first action `resume` | **pass** (reviewed `4a92d74`, plan `67a62c31…`) |
| 9 | PILOT-FEAT-01 | reviewer v1 | `01a116b7-b5ea-7282-a914-93ab4ee6d74c` | 22:15:00 → 22:19:10 | 51,401 tokens | 23 commands (1 recovered lookup) | prior `review.md` (`851a7bd`, sha `8bc6e0e6…`), logs | none | re-ran both acceptance commands; hashes | `changes_requested` — sole finding: unfilled `handoff.md` |
| 10 | PILOT-FEAT-01 | re-reviewer | `01a116cb-90b0-7d51-beb4-4661625912e6` | 22:36:42 → 22:40:25 | 65,395 tokens | 31 commands, all green | `feature/review.md` (`09580e6`, sha `5e41b751…`), logs | none | placeholder probe (no matches); re-ran acceptance; first action `resume` | **pass** (reviewed `98a2720`, plan `349913c6…`) |

Wall-clock windows bound commit/claim times and include orchestration; they are
not pure model time. No per-command rejection remains in #8–#10.

## Findings

1. **A cheap scout produced correctly-anchored, decision-ready evidence** for
   both tasks (DQ/F traceability, scoped negative searches, no critical UNKNOWN),
   and the final independent audit found **no wrong anchors**. (Observed here;
   not a general claim about all tasks.)
2. **Cross-Harness handoff works and is genuinely clean-context.** Both reviews
   were performed by fresh Harness-B sessions receiving persisted artifacts only
   (first action: `resume`), and the feature even demonstrated the full loop:
   B review → recorded rework on A → fresh B re-review → `pass`.
3. **The dominant harness failure had a concrete fix.** Default `codex exec` on
   this Windows host rejects every command under its session policy (39 rejected
   invocations in #7); `-c windows.sandbox="unelevated"` makes the read-only
   sandbox usable (86 green commands in #8–#10). Recorded in
   [runbook.md](runbook.md) §8 for reproducibility.
4. **Byte-exact gate × `core.autocrlf=true` is real friction**: three
   `set-gate` re-attestations during the pilot, and archive byte-form recovery.
   Candidate follow-up (separate Ticket), not fixed here.
5. **`validate: OK` does not prove the review criteria passed.** The unfilled
   handoff template passed structural validation and task completion; only the
   independent reviewer caught it, and the rework loop resolved it. This is the
   pilot's clearest evidence for the tracker's "structural validity ≠ criteria
   pass" rule and is a candidate follow-up (placeholder detection), separate
   from this Ticket.
6. **No cost or savings claim is possible or made.** Only codex tokens exist
   (205,882); Trae-side usage is UNKNOWN; there is no comparable measured
   baseline, and tool-call counts alone do not establish monetary savings.
7. **Task sizing / defaults**: both tasks were tiny and scouting was
   proportionate; the one extra round (feature rework) was administrative and
   discovered by the intended mechanism (review), so no task-size or Scout
   instruction change is recommended from this pilot.

## Practical limits and UNKNOWNs

- Trae-side sessions expose no tokens/cost/tool counts; their session ids are
  not persisted (state claims carry only harness/model/timestamp). UNKNOWN.
- The 3 pre-fix blocked attempts and 4 probes kept no logs; details UNKNOWN.
  Only their observable effect (before/after #7 vs #8) is recorded.
- Single host, single day, tiny tasks, one Python (3.13.5); results are
  observations, not generalizable measurements.
- The archived artifacts match the bound byte forms in this worktree; a fresh
  checkout with `core.autocrlf=true` may re-normalize line endings (see the
  friction section).
- No synthetic records were written; failures above are preserved as measured
  outcomes.

## Follow-up candidates (separate Tickets — nothing fixed here)

1. v2 byte-exact gate vs `core.autocrlf=true` (stale gate after branch
   switches/checkouts) — consider stable byte handling or clearer re-attest path.
2. Handoff completeness is not checked by `validate`/`resume` (placeholder
   handoff passed until review); consider a placeholder detection check.
3. Windows codex launch guidance (`-c windows.sandbox="unelevated"`) is recorded
   in this pilot's runbook; a durable config/trust fix, if wanted, is a separate
   change.

## Acceptance assessment (cross-reference to issue 08)

- Live sessions: scout, senior, executor, and independent reviewer sessions —
  all real; independent reviews ran on a second actual Harness (B). Met.
- Cross-Harness handoff: performed at both review boundaries, persisted
  (`review.md` hash-bound in `state.yaml`), receivers without sender
  conversation. Met.
- Anchors/DQ-F/scope/UNKNOWN/handoff: audited; no wrong anchors. Met.
- Repeated exploration / targeted rereads / gaps / rework: recorded; one rework
  loop, no escalation. Met.
- Models/Harnesses/time/tool activity/usage: recorded as far as observed;
  UNKNOWNs labelled. Met.
- Usefulness assessed separately from CLI validity: yes (finding 5). Met.
- Availability condition: recorded while it existed; resolved at run time; no
  simulation used. Met.
- Local publication with artifact links; follow-ups as candidates, no hidden
  scope. Met.

The pilot supports the pilot decision: structured cheap-scout → senior handoffs
worked across two real Harnesses on small tasks, with the observed costs being
one administrative rework loop and two environment-level frictions (sandbox
policy, CRLF byte gates) — both recorded for separate follow-ups.

## Durable package (HARDEN-006, 2026-10-09 — appended; original run results above are untouched)

The archived ticket artifacts are now preserved as verified ZIP packages
produced by the kit's `artifact_archive.write_archive`:
[pilot/bug/artifacts.zip](bug/artifacts.zip) and
[pilot/feature/artifacts.zip](feature/artifacts.zip). All eight
Evidence/Audit/Plan/Review hashes were verified against the recorded
`state.yaml` bindings BEFORE packaging, from the archived working bytes only
(no checkout, edit, or re-gate of the original target; no recomputed
replacements). Bound members carry the recorded hash; unbound supporting
files (`decision.md`, `progress.md`, `handoff.md`, `state.yaml`) carry
computed hashes and a null `bound_sha256` in each `manifest.json`
(`format_version: 1`). Members use the artifacts' original repository paths,
with the registered Plan at its actual source path (`.scratch/<TICKET>/plan.md`);
`snapshot_head` is the recorded branch evidence from this report (`pilot/bug`
head `a1cbdab`, `pilot/feat` head `aea68a6`). Verification details, the full
path mapping, supporting-file hashes and the fresh-clone re-verification are
recorded in [archive-manifest.md](archive-manifest.md).
