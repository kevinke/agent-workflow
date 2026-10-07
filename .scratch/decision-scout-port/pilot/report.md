# Pilot Report — Measured Live Model/Harness Handoff (SCOUT-008)

Status: **PENDING — real Harness-A sessions were run; the required cross-Harness
handoff could not be performed, so no acceptance criterion is passed.**
Date: 2026-10-07 (Task 1 prepared; Task 2 executed 2026-10-07). Runs performed:
**2 real Harness-A role sessions** (scout, senior) plus **3 attempted Harness-B
(codex) sessions, all blocked by environment policy**.

Procedure: [runbook.md](runbook.md). Plan Task 2, spec Testing Decisions, issue
[08-live-model-harness-pilot.md](../issues/08-live-model-harness-pilot.md).

## Consent and budget

The user's explicit consent to spend external model quota was given on 2026-10-07
with a budget of **at most 5 model sessions, each at most ~3 minutes**, and
**option A** (Harness A = this Trae session and its subagents; Harness B = the
`codex` CLI). Session budget actually consumed:

| # | Role | Harness | Outcome |
|---|---|---|---|
| 1 | scout (cheap) | A (Trae subagent) | produced real evidence for both tickets |
| 2–4 | — (3 attempts) | B (`codex` CLI) | **all blocked by session policy** before any useful work |
| 5 | senior (audit + decision + plan) | A (Trae subagent) | produced audit/decision/plan for both tickets |

**The budget is exhausted (5/5).** The executor and independent-reviewer sessions
(Task 2 Steps 1–2) were therefore **not run**; completing them needs 2 sessions
beyond the stated cap, which was not authorised.

## What actually happened (Task 2, Steps 1–2)

Two long-lived role sessions ran on **Harness A** in the disposable target
`%TEMP%\scout008-target` (git repo, base commit `2fee994`), on two isolated
branches so the bug and feature cannot interfere (merge-base = the shared root
commit; neither branch leaks into the other).

**Session 1 — scout (cheap), Harness A.** Wrote `evidence.md` round 1 for both
tickets and committed it:

- bug `PILOT-BUG-01` evidence committed at `0504a25` (observed_commit `b5a13a8`),
  4 findings F-01..F-04, DQ-01..DQ-03 all ANSWERED, no critical UNKNOWN.
- feature `PILOT-FEAT-01` evidence committed at `d5234df` (observed_commit
  `0a98f42`), 5 findings F-01..F-05, DQ-01..DQ-03 all ANSWERED.

**Session 5 — senior (evidence-auditor → technical-decision → executor-plan),
Harness A.** Audited sufficiency, wrote `decision.md`, wrote `plan.md`, and the
gate verdict `sufficient` round 1 was recorded:

- bug `a947051`; feature `b856779`.

Neither session saw the other's conversation, but **both ran on the same Harness**
(A). The required cross-Harness handoff (issue AC 2; plan Global Constraint "at
least one handoff must cross two actual Harnesses") is therefore **unmet**.

## The Harness-B blocker (why AC 2 cannot be met here)

Harness B was `codex` CLI `C:\nvm4w\nodejs\codex.ps1` (`codex-cli 0.160.0`,
ChatGPT login). Three attempts to run a receiver session in the disposable target
were made with:

```
codex exec -C <target> -s workspace-write --skip-git-repo-check \
  -c approval_policy="never" --color never -o <file> -      # prompt on stdin
```

All three sessions were refused by the environment **before any useful work**:
`Blocked by session policy` / the environment is reported read-only, and even a
plain read of a file, and `resume`, were rejected. Diagnosis:

- `~/.codex/config.toml` sets `runCodexInWindowsSubsystemForLinux = true`, and the
  **project trust allowlist does not include the disposable target** (it lists
  `d:\Code\agent-workflow` and `/mnt/d/Code/agent-workflow`, but not
  `%TEMP%\scout008-target`).
- Per-invocation overrides were tried and **failed**: `-c approval_policy="never"`
  and `-c projects.'<target>'.trust_level="trusted"`.

Conclusion: on this host, the `codex` CLI cannot be driven non-interactively from
a temp target under its current configuration. **A real A→B handoff cannot be
persisted from here**, so the pilot cannot satisfy AC 2 and stays pending. This is
an environment/configuration blocker, not a missing-tool blocker: `codex --version`
responds, so the tool exists; the session policy refuses to run it.

## Where the work stands in the disposable target

Both tickets reached `implementation` through the real v2 contract path, with a
**registered Plan** and a clean `validate`:

- `PILOT-BUG-01` — final commit `bc290ef`; `phase: implementation`,
  `gate=sufficient round=1`, plan registered (1 task), `validate: OK`.
- `PILOT-FEAT-01` — final commit `193cf8f`; `phase: implementation`,
  `gate=sufficient round=1`, plan registered (1 task), `validate: OK`.

No task was executed: `implementation.current_task = 0/1` for both. `progress.md`
and `handoff.md` in the target are still unfilled templates, and no `review.md`
exists — because the executor and reviewer sessions were not run.

## Observed friction (a real finding)

The v2 gate binding is byte-sensitive, and the host's `core.autocrlf=true` rewrote
line endings when branches were switched, changing artifact bytes and making the
recorded gate **stale** (`validate` → "evidence-audit.md changed since the evidence
gate was recorded"). The binding had to be **re-attested** with `set-gate` after
normalising the audited bytes (bug `a8e7f0b`/`bc290ef`, feature `193cf8f`). This is
observed friction between a v2 byte-exact gate and a CRLF-normalising checkout, and
belongs in a separate follow-up Ticket (see below), not in hidden scope growth.

## Anchor audit (plan Task 2 Step 3 — partially performed)

Verified independently against the actual files at both branches:

- `service.py:1-6` — `CachedValue` has exactly `__init__` (lines 2–3) and `read`
  (lines 5–6); `self._value = config["value"]` at line 3. **Matches** F-01 (bug) and
  F-02 (feature).
- `demo.py:1, 5-10` — import at line 1, `main` builds `{"value": 1}` at line 5,
  constructs at line 6, mutates `config["value"] = 2` at line 8, calls `read()` at
  lines 7 and 10. **Matches** F-04 (bug) / F-04 (feature).
- Runtime claim re-run: `python demo.py` → stdout `initial=1` / `configured=2` /
  `actual=1`, exit `0`. **Matches** F-02 (bug) / F-03 (feature).

Every pivotal anchor inspected is **correct**; neither evidence report contains a
wrong or missing anchor within its declared scope. The negative searches are scoped
as declared (target root `*.py` only, excluding the vendored
`.ai/workflow/examples/scout-fixture/` copy).

## Session records

| Task | Role | Model label | Harness | Window (commit times, +0800) | Usage | Output artifacts | Repeated exploration | Targeted verification | Outcome |
|---|---|---|---|---|---|---|---|---|---|
| PILOT-BUG-01 | scout | DeepSeek-V4.1-Flash | A (Trae) | 20:06 → 20:12 | UNKNOWN | `bug/evidence.md` (`0504a25`) | UNKNOWN | runtime repro | evidence produced |
| PILOT-FEAT-01 | scout | DeepSeek-V4.1-Flash | A (Trae) | 20:06 → 20:13 | UNKNOWN | `feature/evidence.md` (`d5234df`) | UNKNOWN | runtime repro | evidence produced |
| both | senior (audit→decision→plan) | DeepSeek-V4.1-Flash | A (Trae) | 20:14 → 20:37 | UNKNOWN | `*/evidence-audit.md`, `*/decision.md`, `*/plan.md` (`a947051`, `b856779`) | UNKNOWN | anchor re-check | gate `sufficient`, plan registered |
| both | receiver attempt ×3 | `codex-cli 0.160.0` | B (codex) | 2026-10-07 | UNKNOWN | none | — | — | **blocked by session policy** |

Wall-clock windows are bounded by commit timestamps and include the controller's
orchestration; they are not pure model time. Token/cost usage and per-role tool-call
counts were **not captured** and remain **UNKNOWN** — do not infer savings from the
absence of these numbers.

## Findings

1. **A cheap scout on Harness A produced correctly-anchored, decision-ready
   evidence** for both a bug and a feature, with DQ/F traceability and scoped
   negative searches; an independent re-check found **no wrong anchors**. (Observed
   on this pilot; not a general claim about all such tasks.)
2. **The required cross-Harness handoff could not be exercised** because the
   `codex` CLI is blocked by host session policy for the disposable target. The
   value of a cheap-scout → senior-handoff *across* Harnesses is therefore **not
   measured** here.
3. **Observed friction:** a byte-exact v2 evidence gate plus `core.autocrlf=true`
   forces re-attestation after a branch switch. Recorded as a follow-up candidate.

No measured comparison of repeated exploration or cost between roles is claimed,
because no baseline and no usage telemetry were captured.

## Practical limits recorded

- Tool-call counts alone do not establish cost savings; no fabricated percentage.
- Unavailable token/cost data stay `UNKNOWN`.
- A run without the required **actual cross-Harness** pairing is an unmet
  prerequisite, not a successful simulated outcome.
- Structural validity (`validate: OK`) is not proof that acceptance criteria passed.
- Any needed fixes become separate follow-up Tickets.

## Next step (to finish Task 2 Steps 1–2, still blocked)

1. Make Harness B runnable non-interactively: either add the disposable target to
   the `codex` project trust allowlist (and/or disable
   `runCodexInWindowsSubsystemForLinux`), **or** designate another Harness that can
   be driven headlessly.
2. If the user raises the session budget, run the executor (bounded task) and an
   **independent-context** reviewer per ticket, with the handoff for at least one
   ticket crossing Harnesses A→B.
3. Then audit anchors, compare expected vs actual, and replace this pending report
   with the measured report.

Until then this report stays **pending** and **no acceptance criterion is passed**.