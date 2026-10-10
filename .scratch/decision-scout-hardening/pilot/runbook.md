# HARDEN-009 paired-Harness pilot runbook

Status: prepared; live launch pending prerequisites
Prepared: 2026-10-10
Authority: [development plan](../../../../docs/superpowers/plans/2026-10-08-harden-09.md),
[issue](../issues/09-paired-model-pilot.md), supplemental spec C9, and the installed
Workflow Protocol and artifact contracts. This runbook adds no Protocol rule.

## Launch gates

- Confirm predecessors 01-08, 10 and 11 against their actual accepted evidence.
- Capture an exact inexpensive model supported by the selected account. The
  first candidate is Qoder CLI / Qwen3.8-Flash, selected explicitly from its
  returned model list; ZCode / GLM-5.3-Flash is the supervised desktop alternative.
  Auto, a capability tier, or a silently substituted model cannot establish identity.
- Record the exact, different senior Codex CLI model and its configuration/
  runtime identity sources; a workflow `claim` is an advisory label, not proof.
- Establish the selected Codex Reviewer's session tool-write restriction on
  this host/build with a disposable protected sentinel. Writes to live source,
  tests, fixtures, config and Git metadata, and supervisor metadata, must fail;
  the supervisor must re-enumerate unchanged bytes. An ordinary worktree,
  permission banner or prompt prohibition does not satisfy this gate.
- Obtain and persist a new explicit budget authorization before any model
  launch, including a paid smoke or policy-rejected attempt. Existing SCOUT-008
  allocation is exhausted and is never reused.

Until all gates hold, prepare files and run non-model diagnostics only. An
unsupported reviewer boundary blocks the complete live pilot.

Exception for establishing the gate itself: after the explicit budget grant,
one counted isolated smoke may test the candidate Reviewer session boundary
before inexpensive-model login is available. This is a diagnostic, not a pilot
leg or an acceptance verdict. A rejected launch stops without automatic retry.

## Session matrix and proposed budget

| Leg | Runtime/model | Fresh context | Output and limits |
| --- | --- | --- | --- |
| Scout | Qoder CLI / exact Qwen3.8-Flash, or ZCode / exact GLM-5.3-Flash | New task, no old discovery chat or project-memory injection | Structured Evidence/Handoff; bounded DQ investigation |
| Audit, decision, Plan | Codex CLI / explicitly selected different senior model | New `codex exec`; first repository action is workflow resume | Bound audit, decision and registered execution contract; targeted rereads |
| Executor | Selected inexpensive Harness/model | Separate bounded session | Implement registered task, verify, update Progress/Handoff |
| Reviewer | Codex CLI / explicitly selected senior model | Independent new context over prepared snapshot | Technical candidate Review/Handoff; no live writes or publication |

Authorized cap: **six total model-launch attempts**, with four core legs and at
most two additional attempts for smoke, failure or rework. All policy-blocked
launches count. If one extra attempt is used for a smoke, only one extra remains.
Count free/promotional model launches too; neither free pricing nor existing
subscription quota removes the attempt cap. No automatic retry or renewal.

Authorized billing constraint: use available subscription/promotional quota only;
no purchase, top-up or separate API billing. The user granted this cap in the
current session; the wording and recording time are preserved in report.md.
Set and record a per-leg wall-time limit (proposed 15 minutes), available
turn/token limits and the launch argv; exceeding a limit stops that attempt.

## Prepare the disposable target

1. Select an accepted kit revision; record full commit identity and raw hashes
   of the three starting fixture files and `task.md` before any model sees them.
2. Create a new disposable directory outside the kit/live worktree. Copy only
   `fixture/config.py`, `fixture/cache.py`, `fixture/test_behavior.py`, and
   `task.md` into a separate Git repository with independent Git metadata.
3. Install the repaired kit with `python3 <kit>/scripts/ai-workflow/main.py init
   --with-skills`. Use a disposable author identity when committing this target;
   do not copy personal paths, account details or model preferences into project files.
4. Add a thin Qoder project-skill entry only if needed to discover the installed
   roles. Its contents point at the authoritative installed role/Protocol files;
   do not duplicate their rules or change kit-wide installation behavior.
5. Make the public CLI reachable as `ai-workflow` by a local launcher outside
   the tracked target. Run its version/help/validate diagnostics without a model.
6. Start Ticket `PAIR-01`, reference `task.md`, enter `evidence_collection` via
   public commands, and commit the frozen requirement boundary. Record the
   target HEAD, branch, dirty state and byte manifest. Do not seed findings,
   audit, decisions, Plan or a technical verdict on behalf of the models.
7. Run the frozen five-case acceptance command and record the expected missing-
   reload baseline separately from the kit suite.

Any executable sketch must use actual installed help; placeholders above are
parameters to resolve and record, not commands claimed to have run.

## Evidence transfer and execution

Each role starts with `ai-workflow resume PAIR-01`, follows State's phase and
role, and reads the authoritative Protocol/roles/contracts plus only the required
artifacts and fixture. Here **resume means the workflow CLI**, never continuation
of an old model chat. Do not use Codex/Qoder chat resume, fork, automatic memory,
unlisted MCP sources, or prompts embedding prior discoveries. Record loaded
instruction/configuration sources and any unavoidable context limitation.

The receiving inputs are frozen task/DQs, target State, role-required Evidence,
Audit, Decision, registered Plan, Progress, Handoff and Review, fixture, and
public Protocol/contract documents. Model prompts contain role/scope/budget
instructions and these paths, not a separate narrative summary of findings.

Record each model's version, displayed/model ID, identity source, launch argv,
thread/task identity, UTC launch/finish times, exit status and raw prompt/output.
Record the receiver's first action and log-backed source rereads. Distinguish
targeted anchor verification from repeated broad exploration. Keep failures,
rework and edited artifacts, with raw-byte digests and revision identities.

Audit/decision/Plan may share one senior session; their public phase transitions
and artifact bindings remain separate. Implement only the registered contract.
Escalation or failed behavior acceptance consumes the remaining cap honestly.

## Reviewer and trusted publication

The trusted coordinator prepares the independent snapshot, never the Reviewer:

```text
ai-workflow prepare-review PAIR-01 --commit <literal-full-oid> --output <new-context>
ai-workflow run-review PAIR-01 --review-context <context> --kind baseline -- <argv...>
ai-workflow run-review PAIR-01 --review-context <context> --kind probe -- <argv...>
ai-workflow set-review PAIR-01 --verdict <reviewer-verdict> \
  --review-context <context> --report <context>/scratch/review.md \
  --handoff <context>/scratch/handoff.md
```

The Reviewer works only on the prepared snapshot and designated scratch area.
The existing `linux-bwrap-v1` supervisor records both baseline and probe receipts;
the report cites every receipt and distinguishes modified probe tests from frozen
baseline acceptance. The trusted coordinator publishes the Reviewer's exact
technical report, without adding findings, repairing sources or issuing a verdict.
Publication checks the current live commit, Plan, inputs and byte identities.
A mismatch requires a fresh snapshot and new independent review, within budget.

**Adapter gap:** a Codex CLI session with unrestricted live tools cannot gain
support merely by putting selected tests through `run-review`. Conversely the
existing boundary disables networking, credentials and inherited configuration,
so it cannot directly host an entire networked model session. Demonstrate the
Reviewer session boundary and its supervisor handoff before launch; do not alter
the frozen profile or fabricate receipts to bypass this gap. Current product
documentation and a cost-free sandbox-helper probe are supporting diagnostics,
not evidence that the real Reviewer session has passed.

## Results, stop criteria and transport

- Stop on absent exact models/auth/quota/budget, ineffective live-write denial,
  launch/policy rejection, unexpected live/meta write, missing receiver fresh
  context, exhausted time/attempt limit, or a deviation requiring a new decision.
- No global permission changes, sandbox bypass, hidden automatic retries, or
  retry loops. Preserve the actual failure and publish a pending/failed report.
- Passing needs all five behavioral cases, actual differing Scout/decision
  identities, cross-Harness fresh receiving context, credible DQ/F artifacts,
  independent isolated Review and current bindings. Validation alone is insufficient.
- After passing, use `archive-artifacts` with its installed help to export only
  current verified bindings. On failure retain available raw artifacts; do not
  create a package implying the successful-export gate passed.
- Measure elapsed time and traceable token/cost sources. Missing telemetry stays
  UNKNOWN. Tool counts are not monetary savings; without a comparable baseline,
  report no savings percentage.
- Raw authentication URLs/tokens and private configuration never enter committed
  logs. Keep private originals outside the repository; disclose any necessary
  log redaction and retain the distinction between originals and publishable copies.
- Update HARDEN-009 acceptance/status and ticket index only from actual live
  evidence. Historical SCOUT-008 artifacts and completed status remain unchanged.
