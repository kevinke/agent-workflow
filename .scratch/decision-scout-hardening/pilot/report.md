# HARDEN-009 / PAIR-01 pilot report

Status: actual paired pilot passed; PAIR-01 is `done`, current Review `pass`
Date: 2026-10-10
Kit base: `3aa9fc6700ad89485cdde1a7d8f993ac3754bcf2`
Branch: `codex/harden-009-pilot`; local delivery, no remote publication
Pilot model-launch attempts: **8**, including all failed/diagnostic starts

## Authorization and limits

The original grant was six attempts: “授权，按上述 6 次和现有额度执行”,
recorded at 01:30 UTC. After three starts, the user explicitly superseded that
cap: “你可以重置下额度试试，或者根据你的需要追加，不用限那么死。你再看看怎么解决”.
The additional authorization was recorded at 02:55:41 UTC. All historical
attempts remain counted; neither accounting nor provider quota was reset.
Only existing Codex subscription and available Qoder quota were used, with no
purchase, top-up or additional API billing. Each live role was limited to 900
seconds, and each launch was recorded before starting; no automatic relaunch.
The conservative ledger is [budget-ledger.json](logs/budget-ledger.json).
A ninth launch is the final whole-branch documentation/evidence review,
accounted separately from the four PAIR-01 roles: fresh read-only Codex app
subagent with explicit gpt-5.6-sol over fixed base/head. It is not another formal
PAIR-01 review or pilot rerun. See `logs/09-final-review-launch.json`. The independent branch review reproduced
the bundle, five cases and raw archive bindings, and found one Important stale
index-status contradiction (no Critical/Minor findings). The coordinator fixed
the current index/issue descriptions in one pass; a cross-document consistency
check failed before the correction and passed afterwards. No second model
review was launched. The original response is [final review](logs/09-final-review.md);
all coordinator rulings and their limits are [recorded](logs/09-coordinator-rulings.md).

## Actual models and transfer

| Role | Harness / configured model | Identity and freshness evidence | Actual result |
| --- | --- | --- | --- |
| Scout, attempt 5 | Qoder CLI 1.1.67 / Qwen3.8-Flash | Account `--list-models`, explicit argv, runtime `system.init.model`; new session; first tool workflow resume | Structured Evidence/Handoff, 28 tool attempts; 354.774s, exit 0 |
| Audit/decision/Plan, attempt 6 | Codex CLI 0.162.0-alpha.2 / gpt-5.6-sol | Explicit `--model`; fresh auth-only client home, ephemeral session, no chat resume; first repository tool workflow resume | Bound sufficient audit, Decision, registered one-task Plan with zero pre-completed tasks; 267.604s, exit 0 |
| Executor, attempt 7 | Qoder CLI 1.1.67 / Qwen3.8-Flash | Explicit argv and runtime init; different fresh config/session; workflow resume first | `config.py` only, five tests pass, public complete-task; 215.893s, exit 0 |
| Independent Reviewer, attempt 8 | Codex CLI 0.162.0-alpha.2 / gpt-5.6-sol | Fresh whole-process enclosure and read-only tools over independent snapshot; workflow resume first | Baseline and independent probe receipts, exact candidate `pass`, guarded publication; 197.455s, exit 0 |

The Scout and senior selections differ and the transfer crosses Qoder → Codex.
Claims in State are advisory labels. The recorded account/config/runtime sources
establish the selected identities; no provider-side backend-model attestation is
available. Read [paired-role-traces.json](logs/paired-role-traces.json) and each
numbered launch/event file for the actual first actions and unique sessions.

Receiver inputs were persisted State, frozen task, Evidence/Handoff and the
installed Protocol/contracts/roles, followed by the receiver's own Audit,
Decision and Plan. No old Qoder conversation, unapplied attempt-3 candidate,
prompt-supplied findings or hidden summaries were transferred. Fresh private
configuration roots copied authentication/installation identifiers only; memory,
old chat, MCP and plugin inheritance were disabled. Codex's shipped builtin
system skills are not previous project memory; none was read for this task.
Three coordinator acknowledgments supplied only commit/hash mechanics between
senior phases, never findings. All three phase-boundary commits are logged.

## Frozen inputs, decisions and behavior

The frozen task is [task.md](task.md); starting source/tests are in `fixture/`.
The fresh retry target began at `f507bfa10b3920fbb52aed118686af8669c50926` with
independent Git metadata, branch `pilot`, no dirty paths and the same four input
hashes as the original preparation. [Retry manifest](logs/04-target-baseline.json).
The rejected first target started at `7e40f2b9de4bbdb4007b07a2578da1b68a708fcb`;
its incomplete artifacts were retained privately and never seeded into the retry.

Scout DQ-01/02/03 findings covered instance ownership/lifetime, parser/error
semantics, and the verification seam. The senior audited and bound those facts,
then chose replacement-before-assignment at the `Config` boundary. The registered
Plan protected `cache.py`, tests, task and installed docs, allowing implementation
only in `config.py`. The executor retained a private instance path and added
`reload()` that constructs a replacement `ValueCache` before assigning it.

Readable raw outputs: [Evidence](logs/05-evidence.md),
[Audit](logs/06-evidence-audit.md), [Decision](logs/06-decision.md),
[Plan](logs/06-plan.md), [implementation](logs/07-final-config.py),
[Progress](logs/07-progress.md), [independent Review](logs/08-review.md).
Accepted raw artifact bytes are also in [artifacts.zip](artifacts.zip).

The starting suite had two passes and three errors solely for missing
`Config.reload`. Actual executor and coordinator runs passed all five frozen
cases. The isolated Reviewer baseline used `python3 -B -m unittest discover
-s . -p test_behavior.py -v` (bytecode-disabled equivalent of the frozen command)
and independently passed all five with exit 0:

- `test_reads_initial`
- `test_cached_until_reload`
- `test_reload_valid`
- `test_bad_reload_preserves_previous`
- `test_instances_isolated`

The Reviewer authored a separate probe for exact prior-cache object preservation
on failure, all old values, existing `ValueError` text, successful replacement,
and `None` return. Its receipt also has exit 0. Both receipts record unchanged
before/after snapshot identity and empty changed/added/removed path lists. Probe
fixtures were temporary files under the verifier's `/tmp`, cleaned by
`TemporaryDirectory`; no snapshot edits or restoration were claimed.

## Isolation, publication and currentness

The model client and verifier use separate measured boundaries:

1. The entire Reviewer CLI and code-mode companion ran in a private bwrap mount
   namespace with `/snapshot`, `/scratch`, RO runtime/readback and separate
   auth-only `/client-home`. Real target and supervisor meta were absent. The
   current session's shell attempted six protected sentinel writes and received
   `EROFS` (30) each. The Reviewer reported the requested file-tool rejection
   under the read-only policy; denied file edits do not produce a separate
   `file_change` item in this CLI's JSONL, so that exact refusal is model-reported,
   not an independently logged file-change event. Host byte/mode rechecks showed
   all sentinels and the actual live repository unchanged. This client enclosure
   shares networking for the model and is **not** the no-network verifier profile.
2. Every technical verifier command was authored by the Reviewer, emitted as a
   request, and manually transported unchanged to public `run-review` by the
   trusted coordinator. Actual supervisor receipts record `linux-bwrap-v1`,
   `enforced=true`, 29 denial attempts, denial errnos 18/30, network refusal 101,
   only HOME/LC_CTYPE/PATH/PWD inherited, and live/meta/host mounts unavailable.
   The native WSL supervisor and sandbox host were recorded honestly as Linux,
   not the earlier Windows-host example. True metadata copies/hashes returned
   through RO `/readback`; model client credentials were outside verifier scratch.

Baseline receipt: `ac12fced1d1e4affb8387351985f4195`.
Probe receipt: `fcce795c20a44900978fc6cfe3d23d4e`.
Both are cited in the Reviewer-authored reserved provenance block. The coordinator
materialized only the two final JSON strings as candidate UTF-8 bytes, supplied
no technical findings/verdict, and invoked guarded `set-review`.
[Publication record](logs/08-publication.json) confirms exact Review/Handoff byte
agreement at publication. The Handoff was subsequently updated only for actual
checkpoint completion; the bound Review bytes remain unchanged.

Reviewed commit: `2e173aa0d33fca082cbc0dc2da951c24a6c59ed7`.
Completion/export commit: `a2f82c7b7dae60e8f9560edee503f826cd5177aa`.
Final validate/resume returned 0, phase `done`, no executable next action,
current sufficient Evidence/Audit, registered Plan and current `pass` Review.
The target was clean. An existing transport warning remains for root `plan.md`
without explicit `-text`; its current bytes match. Older Evidence anchors were
explicitly reassessed by senior and Reviewer after the implementation.

The generic [client container](logs/reviewer-client-container.py),
[launch/mount/runtime record](logs/08-reviewer-launch.json),
[supervisor original hashes](logs/08-supervisor-original-hashes.json) and
numbered receipts preserve the observed route. No production workflow code,
verifier profile, global permission or historical SCOUT-008 record changed.
This establishes this CLI/build/host arrangement only; Desktop/MCP, native
Windows sessions and other hosts retain their prior limitations. The coordinator
is trusted; matching receipts do not prove the natural-language judgment.

## Failures and operational deviations retained

| Attempt | Outcome | Elapsed seconds |
| --- | --- | --- |
| 1, Codex diagnostic | Missing shipped code-mode companion; shell/file actions unexecuted despite launcher exit 0; no isolation claim | 17.820 |
| 2, Codex diagnostic | Companion packaged; actual shell denials and model-reported file rejection; host recheck unchanged | 18.489 |
| 3, Qoder Scout | Three permission denials, required Evidence write refused; stopped, candidate remains unapplied | 291.831 |
| 4, Qoder retry | Coordinator skipped `.auth` directory while copying; authentication_failed before repository tools, corrected privately without another user login | 8.547 |
| 5, accepted Scout | Required writes worked with exact absolute Edit rules; one optional `validate --show` denied | 354.774 |
| 6, senior | Audit/decision/Plan passed, frozen inputs unchanged | 267.604 |
| 7, executor | Five tests passed; an extra redirected compound test-log command denied | 215.893 |
| 8, Reviewer | Real isolated baseline/probe and guarded pass, live/sentinels unchanged | 197.455 |

Attempts 5 and 7 continued after their harmless optional-command denials, contrary
to the prompt's stop instruction. These are real operational deviations, not
zero-denial or instruction-compliance successes. The denied commands never ran;
role write scope remained enforced and frozen inputs unchanged. Their role-owned
outputs were retained for independent audit/review because C9 tests pairing,
persisted transfer and independent verification. This pilot supplies **no proof
that these models reliably stop after a policy rejection**. The coordinator also
corrected an early zero-denials commentary after reading the final event.

Attempt 3's failed permission diagnosis was initially an inference. Qoder's
actual retry confirmed exact filesystem-rooted `Edit(//...)` rules cover Write/
Edit; only Evidence/Handoff and the exact frozen test command were added. No
bypass mode, global Bash permission, global settings edit or hidden retry was
used. See [Qoder permission semantics](https://docs.qoder.com/cli/permissions).

## Reads, measurements and limits

Attempt-5 Scout made 28 tool attempts, reading the supplied task, all three
fixture files, role/contracts and artifact scaffolds. The senior made 19
completed shell executions, including repeated State/contracts/phase checkpoints.
Its actual source verification was one targeted command over `config.py` and
`cache.py` with line anchors and Git diff against the observed commit; it did not
repeat whole-tree source discovery or rerun the fixture tests. The independent
Reviewer made 14 completed shell executions, including file enumeration, source/
test reads, trace requests and metadata readbacks. These are different count
semantics; no tool-count savings ratio is inferred.

Codex `turn.completed.usage` records:

| Attempt | Input tokens | Cached input tokens | Output tokens |
| --- | ---: | ---: | ---: |
| 1 | 35,782 | 33,664 | 302 |
| 2 | 36,258 | 33,920 | 435 |
| 6 | 1,393,016 | 1,331,456 | 11,348 |
| 8 | 526,373 | 472,960 | 7,473 |

Qoder successful result events report zero token/cost/credit counters despite
nonempty generation. Those counters are retained, but reliable Qoder token and
monetary measurements are UNKNOWN. Attempt 3 has no normal final telemetry;
attempt 4 reports an authentication failure with no repository tools.
Aggregate pilot process time is 1,372.413 seconds; wall time also includes human
login and coordination and has no comparable measured baseline. Live monetary
cost and a comparative savings percentage are UNKNOWN/not claimed. A read-only
Codex quota observation showed 28% used, 72% remaining at that time, so no free
reset credit was consumed; it is account-wide, not this pilot's cost.

Kit baseline suite ran 488 tests in 484.485 seconds, OK; production code was not
changed and that suite was not repeated without cause. Authentication material,
login URLs and old private configuration remain outside the repository. Published
logs redact personal paths/emails; original stream/metadata SHA-256 values are
retained separately from redacted copies. The original supervisor records remain
private, so public redacted JSON cannot reproduce their original raw-byte hashes.
Raw bound artifacts and the matching target history contain no personal paths.

## Reproduction and acceptance

The preparation fixture is intentionally incomplete. Restore the actual finished
target from [pair01-history.bundle](logs/pair01-history.bundle), using
`git -c core.autocrlf=false clone <bundle> <new-disposable-directory>`, then inspect
`pilot` at completion commit `a2f82c7b7dae60e8f9560edee503f826cd5177aa`.
The bundle contains independent target history, installed roles, frozen inputs,
model-authored outputs and reviewed source; its disposable author identity is
synthetic. Run the frozen command, public validate/resume, and compare every
[artifacts.zip](artifacts.zip) member with its manifest/raw registered binding.
A different host must independently re-establish isolation before another review.
Official installer/build observations and execution details are in runbook/logs;
ZCode's official headless CLI remains unverified and was not substituted.

- [x] Frozen disposable task/DQs, receiving inputs and explicitly authorized budget.
- [x] Distinct actual configured Scout/senior selections, cross-Harness fresh transfer, resume first.
- [x] Independent fresh isolated Review; all five behaviors and a meaningful independent probe pass.
- [x] Targeted rereads, failures, rework, raw artifacts and telemetry provenance recorded; gaps UNKNOWN.
- [x] Historical SCOUT-008 evidence/status/budget untouched.
- [x] Actual guarded publication, done gate and verified artifact export passed.

See [runbook.md](runbook.md), [issue 09](../issues/09-paired-model-pilot.md),
[logs manifest](logs/logs-manifest.json) and [artifact package](artifacts.zip).
