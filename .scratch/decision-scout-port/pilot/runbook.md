# Runbook — Measured Live Model/Harness Handoff Pilot (SCOUT-008)

Status: ready (Task 1 complete). The pilot **report** remains pending; see
[report.md](report.md). This runbook is the reproducible procedure for the actual
runs performed in Task 2. It records only what was actually observed/probed on
2026-10-07; it contains no model outputs, tool counts, or savings.

Plan: [2026-10-07-scout-08.md](../../../docs/superpowers/plans/2026-10-07-scout-08.md)
Task 2. Spec: [spec.md](../spec.md) (Testing Decisions + live-pilot decision).
Issue: [08-live-model-harness-pilot.md](../issues/08-live-model-harness-pilot.md).

## 0. Binding external-budget ruling (record verbatim)

> No task may launch a real model session that spends the user's external
> quota/credentials without the user's consent. Task 1 must ONLY *probe*
> availability and record it — e.g. run version/help checks like `codex --version`,
> `git --version`, verify `ai-workflow --help` works. It must NOT authenticate or
> run any paid/real model session.

Consequence: this runbook records prerequisites and the exact procedure. No real
model session was launched while producing it. Task 2 may only run real sessions
after the user has explicitly consented to spend their external model quota. If
that consent or the required access is absent, the pilot stays **pending with an
explicit blocker** (plan Task 2 Step 5, AC 7). Never write synthetic run records.

## 1. Prerequisites observed (probed 2026-10-07, no session run)

### 1.1 Host environment

| Check | Command | Observed result |
|---|---|---|
| OS / shell | — | Windows; PowerShell 7 |
| Python | `python --version` | `3.13.5` (use `python`, not `python3`) |
| Git | `git --version` | `git version 2.45.1.windows.1` (exit 0) |
| ai-workflow CLI | `python d:\Code\agent-workflow\scripts\ai-workflow\main.py --help` | full usage printed, exit 0 |

CLI invocation (confirmed, do not assume `python -m`):

- Entry point is the file `scripts/ai-workflow/main.py` in the kit repo
  (`d:\Code\agent-workflow`).
- `python -m ai-workflow` **does not work** — there is no `__main__.py` and the
  directory name contains a hyphen (`No module named ai-workflow.__main__`).
- The command root is `os.getcwd()`; every command except `init [target]` acts on
  the current directory. So all pilot commands must run with `cwd` = the
  disposable target.
- `init` / `start` produce `workflow_version: 2` by default (verified: a fresh
  `start` yielded `schema_version: 1` / `workflow_version: 2`).

### 1.2 Available Harnesses (observed)

| Harness | Identity | Probe evidence |
|---|---|---|
| A — Trae IDE session | this session (TraeWork / Trae IDE agent) | current session; file read/edit/grep/glob/shell tools available |
| B — `codex` CLI | `C:\nvm4w\nodejs\codex.ps1` | `codex --version` → `codex-cli 0.160.0` (exit 0) |

Observed absence (searched on `PATH`, 2026-10-07): `claude`, `gemini`, `aider`,
`cursor-agent`, `opencode` — **not found**. Record this as observed absence; do
not substitute a simulated harness for them.

### 1.3 Available models

| Harness | Model label | Basis |
|---|---|---|
| A — Trae session | `DeepSeek-V4.1-Flash` | model label stated in the session environment |
| B — codex CLI | **UNKNOWN** | not determined; pinning a model requires running a session (`codex exec -m <model>`), which Task 1 must not do |

Tier mapping (cheap/senior per [`ROLES.md`](../../../.ai/workflow/ROLES.md)) is a
Harness-local default, not an identity check. The Trae session label above is the
only observed model identity; **do not assume** the codex model, its tier, or any
provider price. Record the codex model at run time once a consented session is
started.

### 1.4 Tool access and transcript/usage availability

| Harness | Tool access | Transcript | Token/cost usage |
|---|---|---|---|
| A — Trae session | read / write / edit / grep / glob / shell — observed in this session | session visible to the operator; not exportable to the repo by the agent | **UNKNOWN** — no token/cost telemetry exposed to the agent |
| B — codex CLI | coding CLI; `exec`, `resume`, `fork`, `apply`, sandbox modes `read-only`/`workspace-write`/`danger-full-access` (from `codex --help`) — declared by the CLI, **not** session-verified | session history + `resume`/`fork` exist (from `codex --help`) | **UNKNOWN** — not confirmed; would need a real session |

Rule: label any unavailable usage number **UNKNOWN**. Never fabricate a savings
percentage, and never infer monetary savings from tool-call counts alone.

### 1.5 Per-target-environment checks

The intended execution environments are the host machine (`git 2.45.1`, Python
3.13.5, CLI entry point present) for both Harnesses — codex runs as a local CLI on
the same machine. Before each real session, re-run in the target directory:

```
git --version
python <kit>\scripts\ai-workflow\main.py --help
python <kit>\scripts\ai-workflow\main.py validate
```

Expected: `git version 2.45.1.windows.1`; CLI usage with exit 0; `validate` prints
findings and exits 0 (non-zero only on ERROR). A per-Harness session that cannot
reach git or the CLI is a blocker to record, not something to simulate.

### 1.6 Prerequisite verdict

- Two Harnesses are present (Trae session + codex CLI) and git + the CLI are
  available → the pilot is **runnable in principle**.
- But the required *actual model sessions* cannot be launched under the Task 1
  ruling, and codex model identity/tier and token telemetry are **UNKNOWN**.
- Therefore the report is **pending** with the explicit blocker recorded in
  [report.md](report.md). Do not mark any acceptance criterion passed until real
  sessions exist.

## 2. Disposable target setup (verified end to end)

Use a throwaway target outside the kit repo. Verified commands (Windows,
PowerShell 7), where `<KIT>` = `d:\Code\agent-workflow`:

```powershell
$T = "$env:TEMP\scout008-target"          # disposable; delete when done
Remove-Item -Recurse -Force $T -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $T | Out-Null
git -C $T init -q
git -C $T config user.email "pilot@example.invalid"
git -C $T config user.name  "Pilot"

# install the protocol (idempotent). CLI root = cwd for everything else.
python <KIT>\scripts\ai-workflow\main.py init $T

Set-Location $T
python <KIT>\scripts\ai-workflow\main.py start PILOT-BUG-01  --title "bug: read after config change"
python <KIT>\scripts\ai-workflow\main.py start PILOT-FEAT-01 --title "feature: CachedValue.reload(config)"
```

Two Tickets on two branches keep bug and feature from interfering:

- Bug: branch `pilot/bug`, Ticket `PILOT-BUG-01`.
- Feature: branch `pilot/feat`, Ticket `PILOT-FEAT-01`.

Copy the fixture into the target root on the branch that needs it, and commit it
as the task's base so anchors have a stable `observed_commit`:

```powershell
Copy-Item <KIT>\.ai\workflow\examples\scout-fixture\service.py $T\service.py
Copy-Item <KIT>\.ai\workflow\examples\scout-fixture\demo.py    $T\demo.py
git -C $T add service.py demo.py
git -C $T commit -q -m "pilot: add scout-fixture baseline"
```

Artifacts are written under `.ai/work/<ticket-id>/` (verified: `start` created
`state.yaml`, `evidence.md`, `handoff.md`, `progress.md`; `decision.md`,
`plan.md`, `evidence-audit.md`, `review.md` appear at their phases).

## 3. Task A — Bug brief (recorded before any model work)

**Ticket:** `PILOT-BUG-01`, branch `pilot/bug`. Files: `service.py`, `demo.py`.

**Defect.** `CachedValue.__init__` snapshots `config["value"]` into `self._value`,
and `read()` returns that stale snapshot. After the caller changes
`config["value"]`, `read()` still returns the original value.

**Reproduction command** (cwd = target): `python demo.py`

Observed **before** the fix (recorded 2026-10-07, verified by Task 1 — this is the
ground truth the model runs are measured against):

```
initial=1
configured=2
actual=1
```

exit 0. The bug is `actual=1`: after `config["value"]` becomes `2`, `read()` must
return `2`.

Expected **after** the fix:

```
initial=1
configured=2
actual=2
```

exit 0.

**Acceptance test** — executor creates `test_bug.py`, reviewer runs it:

```python
# test_bug.py
import unittest
from service import CachedValue


class ReadAfterConfigChangeTest(unittest.TestCase):
    def test_read_returns_updated_value(self):
        config = {"value": 1}
        cached = CachedValue(config)
        self.assertEqual(cached.read(), 1)
        config["value"] = 2
        self.assertEqual(cached.read(), 2)
```

Command: `python -m unittest -v test_bug`

- Expected **before** fix (current): FAIL — `AssertionError: 1 != 2`.
- Expected **after** fix: OK (1 test).

Protected behavior: `read()` before any config change still returns the initial
value; `__init__` keeps its snapshot semantics.

## 4. Task B — Feature brief (recorded before any model work)

**Ticket:** `PILOT-FEAT-01`, branch `pilot/feat`. File: `service.py`.

**Specified replacement behavior (declared now, before model work).** Add:

```python
def reload(self, config: dict) -> None:
```

`reload` replaces the cached value with `config["value"]`, using the *same
extraction semantics as `__init__`* — i.e. it takes a snapshot of the integer and
does **not** retain a live reference to the mapping. It returns `None`. After
`reload`, `read()` returns the new value. `__init__` and `read` semantics are
unchanged. This is the only behavior in scope; no other API changes.

**Acceptance test** — executor creates `test_reload.py`, reviewer runs it:

```python
# test_reload.py
import unittest
from service import CachedValue


class ReloadTest(unittest.TestCase):
    def test_reload_replaces_value(self):
        cached = CachedValue({"value": 1})
        self.assertEqual(cached.read(), 1)
        cached.reload({"value": 5})
        self.assertEqual(cached.read(), 5)

    def test_reload_snapshots_not_aliases(self):
        source = {"value": 7}
        cached = CachedValue({"value": 1})
        cached.reload(source)
        source["value"] = 9
        self.assertEqual(cached.read(), 7)
```

Command: `python -m unittest -v test_reload`

- Expected **before** feature (current): ERROR — `AttributeError: 'CachedValue'
  object has no attribute 'reload'`.
- Expected **after** feature: OK (2 tests).

## 5. Role prompts

All role prompts are delivered through the receiving Harness, which gets the
**repo, the Ticket id, and `ai-workflow resume <ticket>` plus referenced
artifacts — never the sender's conversation.** Point at report paths; do not paste
prior chat. Record each session's Harness, model, and start/end time.

### 5.1 Scout prompt (cheap tier; Harness A planned)

> Repo: `<target>`. Ticket: `<PILOT-BUG-01 | PILOT-FEAT-01>`. Run
> `python <KIT>\scripts\ai-workflow\main.py resume <ticket>` first; you are the
> `scout`. Collect repository facts only and write `.ai/work/<ticket>/evidence.md`
> (Scout Report: Metadata, Decision Questions, Findings, Unknowns, Handoff).
> Use stable DQ/F IDs; each important FACT carries a file/line/symbol anchor
> (`code: <relpath>:<line>-<line> :: <symbol>`) or a runtime anchor (command,
> input, observed result, exit). Draft 3–8 decision questions when none are
> supplied. Distinguish FACT / INFERENCE / UNKNOWN and static / execution / test
> methods; state scope and negative-search exclusions. A critical UNKNOWN does not
> open the gate. Do **not** put design proposals or a sufficiency verdict in
> evidence.md — escalate architectural ambiguity via `ai-workflow escalate`.
> Record the residual changes and stop when the questions are answered or the gaps
> and stopping reason are explicit.

### 5.2 Senior prompt (audit + decide + plan; Harness B planned receiver)

> Repo: `<target>`. Ticket: `<ticket>`. This is a **new, independent context**:
> run `python <KIT>\scripts\ai-workflow\main.py resume <ticket>` and read only the
> referenced artifacts (`evidence.md`, ticket/spec sources). You are the senior
> roles `evidence-auditor` + `technical-decision` + `executor-plan`. Audit the
> report against the four sufficiency questions and record the verdict with
> `set-gate <ticket> --gate sufficient|insufficient --round <n>`; write
> `decision.md`; write `plan.md` (ordered bounded tasks with objective, Fact/
> decision inputs, allowed/protected scope, invariants, acceptance criteria,
> verification commands + expected outcomes, dependencies, escalation conditions)
> and register it with `register-plan <ticket> --path <plan> --total <N>`. Verify
> only the **pivotal** anchors — record which anchor and how; record whether you
> had to survey broadly or only targeted-reread. If the report is insufficient,
> route back to `followup_evidence` instead of guessing.

### 5.3 Executor prompt (cheap tier; consumes the registered Plan)

> Repo: `<target>`. Ticket: `<ticket>`. Run
> `python <KIT>\scripts\ai-workflow\main.py resume <ticket>`; you are
> `ticket-executor`. Execute **only** the registered next task (`next_action.task`)
> — do not redesign or select tasks. Read the registered Plan (`source_artifacts.plan`
> path) and `decision.md`. Make the minimal change; write `progress.md` (completed
> task, files changed, verification commands + results, deviation, open issues);
> commit per task as `ai-workflow(<ticket>): <action>`; update state with
> `complete-task <ticket>`. When unclear or missing tools/repro environment,
> `escalate` rather than inventing design.

### 5.4 Reviewer prompt (senior default; independent context)

> Repo: `<target>`. Ticket: `<ticket>`. This is an **independent context** from
> the implementation. Run `python <KIT>\scripts\ai-workflow\main.py resume <ticket>`
> and inspect the actual change, the registered Plan identity, and the recorded
> verification results. You are the `reviewer`. Re-run the acceptance commands
> yourself; record acceptance-criterion results and the verification
> commands/results in `review.md`; record `pass` or `changes_requested` with
> `set-review <ticket> --verdict <pass|changes_requested>`. Local repairs stay
> within the recorded decision; design/architecture issues escalate. Do not accept
> a phase label as evidence; structural validity is not proof the criteria passed.

### 5.5 Clean-context receiving prompt (cross-Harness handoff)

Use verbatim on the receiving Harness (planned: Scout on Harness A → Senior on
Harness B). The receiver must not inherit the sender's conversation.

> You are receiving Ticket `<ticket>` in repo `<target>`. You have **no** prior
> chat about this work. Establish your own context from persisted state only:
> run `python <KIT>\scripts\ai-workflow\main.py resume <ticket>`, then read the
> artifacts it references (`evidence.md` and, later, `decision.md`, the registered
> Plan, `progress.md`, `handoff.md`, `review.md`). Report your first concrete
> action after `resume` (the "first resumed action"), which artifacts you read, and
> whether the brief was enough to act without a broad re-survey. If the brief is
> incomplete, say exactly what is missing.

## 6. Measurement protocol

For each role session, record one row per session using these fields:

| Field | Meaning |
|---|---|
| Task | `PILOT-BUG-01` or `PILOT-FEAT-01` |
| Role | scout / evidence-auditor / technical-decision / executor-plan / ticket-executor / reviewer |
| Model | observed model label (UNKNOWN if not observable) |
| Harness | A (Trae session) or B (codex CLI), with concrete session id/name |
| Start / end | timestamps (elapsed = end − start) |
| Tool activity | count of **observed** tool actions by that role (reads, greps, edits, shell) |
| Usage | tokens/cost **only if actually exposed**; otherwise `UNKNOWN` |
| Input artifacts | artifact paths the role actually read |
| Output artifacts | artifact paths the role wrote (with sha256 where applicable) |
| Repeated exploration | investigations the senior role repeated that the Scout had already covered (name them) |
| Targeted verification | rereads that were *targeted checks of a pivotal anchor* (name anchor) vs broad re-survey |
| Outcome | observed result: correctness (pass/fail), rework, escalation, first resumed action |

Rules:

- Count only tool actions you can actually observe; label anything unavailable
  `UNKNOWN`. Never infer counts.
- Do not compare cost/savings unless a comparable **measured** baseline exists.
  Tool-call counts alone do not establish monetary savings.
- Preserve failures as measured outcomes; a run without the required actual model
  pairing or the cross-Harness switch cannot satisfy the Ticket.
- Keep every raw artifact; do not paraphrase it away.

### 6.1 Session record template (copy per session)

```
### Session <n>
- Task:            PILOT-BUG-01 | PILOT-FEAT-01
- Role:            <role>
- Model:           <observed label | UNKNOWN>
- Harness:         A (Trae session) | B (codex CLI, session id <id>)
- Start / end:     <ISO> .. <ISO>  (elapsed <m> min)
- Tool activity:   reads=<n> grep=<n> edits=<n> shell=<n>  (observed only)
- Usage:           tokens=<n|UNKNOWN>  cost=<n|UNKNOWN>
- Input artifacts: <paths>
- Output artifacts:<paths (+sha256)>
- Repeated exploration: <named items | none>
- Targeted verification: <anchor checked + how | none>
- Outcome:         <pass/fail, rework, escalation, first resumed action>
- Raw output:      <path to preserved transcript/log>
```

## 7. Artifact locations

- Live workflow artifacts (per Ticket): `.ai/work/<ticket-id>/` — `state.yaml`,
  `evidence.md`, `evidence-audit.md`, `decision.md`, `handoff.md`, `progress.md`,
  `review.md`.
- Registered Plan: a repo-relative path **outside** `.ai/` (e.g.
  `.scratch/<ticket>/plan.md`), referenced and hashed by `register-plan`; it is
  never copied into `.ai/`.
- Continuation brief: `python <KIT>\scripts\ai-workflow\main.py resume <ticket>`
  (read-only; exit 1 when ERROR blockers exist).
- Pilot records produced by **Task 2** (copied verbatim from the disposable
  target): `.scratch/decision-scout-port/pilot/bug/` and
  `.scratch/decision-scout-port/pilot/feature/` — actual State, Evidence,
  evidence-audit, decision, Plan, Progress, Handoff and Review files, plus the
  session records and raw logs.

## 8. Planned handoff across Harnesses (Task 2)

At least one persisted handoff must cross two actual Harnesses with no inherited
sender conversation:

1. Scout runs on **Harness A** (Trae session), writes `evidence.md`, stops with a
   checkpoint-handoff.
2. Senior starts a **fresh** session on **Harness B** (codex CLI), receives only
   `resume <ticket>` + referenced artifacts (prompt §5.5), and records its first
   resumed action.

Record the receiver inputs and the first resumed action for this transition.

## 9. Task 1 self-checklist

- [x] Two observable tasks defined with reproduction/acceptance commands and
      expected outputs recorded **before** model work (sections 3–4).
- [x] Prerequisites probed and recorded (models, two Harnesses, tool/transcript/
      usage availability, `ai-workflow --help`, `git --version`) — section 1.
- [x] Four role prompts + clean-context receiving prompt (section 5).
- [x] Measurement protocol and fields (section 6).
- [x] Artifact locations and cross-Harness handoff plan (sections 7–8).
- [x] Report left **pending**; no synthetic pass; no paid session launched.

> Remaining (Task 2, separate dispatch): obtain the user's consent for external
> model quota, run the real role sessions, persist raw outputs, audit pivotal
> anchors, and fill [report.md](report.md). If that access is absent, keep the
> report pending with the blocker.