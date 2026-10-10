# HARDEN-009 / PAIR-01 pilot report

Status: pending live prerequisites; preparation only
Prepared: 2026-10-10
Kit base: `3aa9fc6700ad89485cdde1a7d8f993ac3754bcf2`
Live model launches: **2 of 6** (two isolation diagnostics; four core legs remain)
New model-session budget: **authorized: at most 6 total launch attempts**

The user authorized the proposed cap in this session: “授权，按上述 6 次和现有额度执行”.
Authorization was recorded on 2026-10-10 at 01:30 UTC. The cap includes isolation
smoke, failures and rework; use only existing Codex subscription and available
Qoder quota, without purchases, top-ups or additional API billing. Stop at six.
No prior SCOUT-008 allocation is renewed.

## Preparation observations

- The independent preparation branch is `codex/harden-009-pilot`.
- Official Qoder native installer fetched bootstrap **1.1.67**, reported matching
  SHA-256, installed successfully, and `qodercli --version` returned `1.1.67`.
  Installation used `--skip-path`; no shell startup file was changed. The actual
  executable name is `qodercli`, whereas current docs use `qoder` in examples.
- Actual `qodercli --help` lists explicit `--model`, `--list-models`, `--print`,
  `--output-format`, configuration sources and tool restrictions. It does **not**
  list the documented `--max-turns` flag. Do not assume that cap exists in this build.
- `qodercli --list-models` exited 1 with `Not logged in`; exact account-time
  Qwen3.8-Flash selection remains UNKNOWN. Browser authentication was initiated
  separately and timed out after five minutes (exit 1). User-side login remains
  required; no authentication URL or token is included here.
- `codex --version` returned `codex-cli 0.162.0-alpha.2`; `codex login status`
  reported ChatGPT authentication. Exact receiving model selection and actual
  Reviewer tool-write restriction remain UNKNOWN.
- ZCode's official installation page describes a desktop app. An official
  headless ZCode CLI remains UNKNOWN; no desktop installation was substituted
  for a verified CLI.
- The five frozen behavior tests ran against the starting fixture: two passed
  (`test_reads_initial`, `test_instances_isolated`) and three errored with
  `AttributeError: 'Config' object has no attribute 'reload'`. This intentional
  incomplete-feature baseline is not successful live acceptance.
- Kit baseline suite: `python3 -m unittest discover -s scripts/ai-workflow/tests
  -p 'test_*.py' -v` exited 0: **488 tests in 484.485 seconds, OK**.
- Cost-free Codex sandbox-helper diagnostic refused a disposable sentinel write
  with `EROFS`; host recheck confirmed unchanged bytes. This helper observation
  does not establish the actual Reviewer session's tool boundary.
- User completed Qoder login. Account-time `qodercli --list-models` returned
  exactly `Qwen3.8-Flash`, including with the fresh private configuration root
  containing copied authentication and installation identifiers only. No old
  chats, rules, skills, plugins or project memory were copied into that root.

Official product sources: [Qoder installation](https://docs.qoder.com/cli/installation),
[Qoder CLI reference](https://docs.qoder.com/cli/cli-reference),
[Qoder model offer](https://docs.qoder.com/events/flashoffer),
[ZCode installation](https://zcode.z.ai/en/docs/install),
[Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode).
Installed help and exit results above describe the actual host/build observed;
documentation claims do not override them.

## Frozen inputs

The experiment is [task.md](task.md) and the three files under `fixture/`.
Disposable-target initial HEAD: `7e40f2b9de4bbdb4007b07a2578da1b68a708fcb`,
branch `pilot`, clean. It is a separate Git repo outside the kit, initialized
with installed roles and PAIR-01 in `evidence_collection` via public commands.
Exact starting byte hashes are recorded in [logs/00-frozen-inputs.json](logs/00-frozen-inputs.json).
The task's DQ-01/02/03 and five acceptance cases are frozen.
The implementation and decision artifacts have not been supplied in advance.
See [runbook.md](runbook.md) for gates, role inputs and proposed six-attempt cap.

## Live session records

Attempt 1 was a separately counted isolation diagnostic, not a workflow leg.
Codex CLI was explicitly configured for `gpt-5.6-sol`; the process exited 0
after 17.820s, but its required code-mode companion executable was absent from
the container. Neither the shell probe nor file edit executed. Protected host
byte/mode manifests were unchanged; this is **not successful model-tool denial
evidence**. See [launch metadata](logs/01-smoke-launch.json),
[events](logs/01-smoke-events.jsonl) and [final output](logs/01-smoke-final.md).
The matching shipped companion was subsequently added to the private read-only
runtime mount and its `--help` succeeded without a model. One bounded packaging
rework is authorized within the same cap; no permissions are weakened.

Attempt 2 completed the same prescribed diagnostic after the runtime packaging
repair: the actual shell executed once and all six protected writes failed with
Linux `EROFS` (30). The actual file-edit request was refused:
`patch rejected: writing is blocked by read-only sandbox; rejected by user approval settings`.
The host manifest comparison confirmed protected bytes and modes unchanged.
Elapsed time was 18.489s, process exit 0. See [launch metadata](logs/02-smoke-launch.json),
[events](logs/02-smoke-events.jsonl), and [boundary/runtime reproduction data](logs/00-boundary-observations.json).
This measures the whole-process container plus Codex read-only tool policy on
this host/build. It does not replace the frozen `linux-bwrap-v1` verifier or
establish PAIR-01 acceptance. A real Reviewer still needs current supervisor
receipts, candidate artifacts and guarded publication.

| Leg | Actual Harness/model | Identity source | Fresh context / resume-first | Result |
| --- | --- | --- | --- | --- |
| Scout | UNKNOWN; not launched | UNKNOWN | UNKNOWN | Pending |
| Audit/decision/Plan | UNKNOWN; not launched | UNKNOWN | UNKNOWN | Pending |
| Executor | UNKNOWN; not launched | UNKNOWN | UNKNOWN | Pending |
| Independent Reviewer | UNKNOWN; not launched | UNKNOWN | UNKNOWN | Pending |

Authorization wording/time, additional billing limit, actual attempts consumed,
per-leg time limits, thread identities, prompts/logs, target revision manifests,
rereads, rework and technical outcomes: pending live execution.

## Acceptance status

- [ ] Frozen disposable target, receiving inputs, authorized cap and stop criteria.
- [ ] Actual Scout/decision models differ; fresh cross-Harness transfer resumes first.
- [ ] Fresh independent isolated Review and five-case passing behavior acceptance.
- [ ] Log-backed rereads, artifact changes, rework and telemetry provenance.
- [x] New explicit available session budget; historical allocation untouched.
- [ ] Actual success/failure outcome and available logs/artifacts published.

## Measurement and limitations

Live elapsed time: UNKNOWN. Live token counts: UNKNOWN. Live cost: UNKNOWN.
Comparable baseline: unavailable. Savings percentage: not claimed.
No real paired-model handoff, Review verdict or passing archive has been produced.
The host's previously measured verifier boundary proves no current model session.
