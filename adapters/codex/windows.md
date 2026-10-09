# Codex on Windows — launch diagnostics (adapter guidance)

When a `codex` CLI session on Windows rejects every shell invocation, this is a
launch/sandbox-policy problem, not a workflow or review problem. This runbook
captures what the SCOUT-008 pilot actually observed and gives a bounded,
stop-on-rejection diagnostic path. It is adapter guidance only: it adds no
workflow rules, no global configuration, and no model policy — the protocol
under `.ai/workflow/` remains the only rule source.

## Observed failure (cited from the pilot; not generalized)

Source: `.scratch/decision-scout-port/pilot/report.md` (§"The Harness-B policy
block and its resolution", §"Session records"). Raw logs:
`.scratch/decision-scout-port/pilot/logs/`.

- On the pilot's Windows host, the first three `codex exec` attempts and the
  first full receiver session (#7) were **blocked before any useful work**:
  every submitted shell invocation returned
  `CreateProcess … rejected: blocked by policy` — 39 rejected invocation lines
  in `logs/codex-review-bug-console.txt`.
- Probing the sandbox launch options (a budgeted, human-directed
  investigation, 4 probes) found a working **per-session** setting:

  ```
  -c windows.sandbox="unelevated"
  ```

  (report line ~94). After it, all receiver commands ran with no policy
  rejection (sessions #8–#10).
- The pilot's Harness-B sessions were **read-only** throughout and were
  launched per session with that flag (report lines ~157/162). The flag
  changes the **Windows sandbox execution mode** so the sandbox can launch on
  that host; the session-policy banner still reports the sandbox as
  **read-only**. It is a per-session override — it does not weaken the
  permission posture and it is not written to any global configuration.

**This is one host, one day, one build (`codex-cli 0.160.0` observed at run
time). Other hosts and builds may differ. Nothing here claims the setting
launches successfully anywhere else — success is established per host by the
diagnostic below, never assumed.**

## Isolated review support on this host: not established

The diagnostics above are launch evidence only. They establish **no**
write-restriction proof for isolated reviewer verification
(`.ai/workflow/PROTOCOL.md` §"Reviewer verification isolation and publication"),
and must not be read as establishing one:

- Nothing in them denies a write to live source, tests, fixtures, configuration or
  Git metadata. No protected sentinel was ever attempted against a Windows
  session, so there is no denial record of any kind (no `EROFS`/`EACCES`/`EPERM`
  observation, no unchanged-sentinel re-enumeration).
- The pilot's read-only **session posture** is a harness policy setting, not the
  per-run enforced boundary the protocol requires: it was never shown to keep a
  verifier process from writing the live tree, it does not separate snapshot from
  live mounts, and it clears nothing about inherited environment, Git overrides,
  descriptors or network reachability.
- `-c windows.sandbox="unelevated"` changed the Windows sandbox **execution mode**
  so the sandbox could launch. It was never measured against live writes, and a
  launch that works is not a restriction that holds.
- A passing helper or mock test on Windows is a test, not a host restriction; the
  protocol says a restriction the unrestricted verifier can undo is not evidence,
  and the same applies to one a test suite asserts on the supervisor's behalf.

Consequently **native Windows sessions and Codex Desktop/MCP are unsupported for
isolated reviewer verification** until their actual host tool-write restriction is
separately demonstrated on the host and build in use. In practice on this
machine `ai-workflow run-review <ticket-id> --review-context <dir> --kind
baseline -- <argv...>` reports a named blocker (the `linux-bwrap-v1` profile needs
an installed `bwrap`, which this host only provides inside WSL), and
`ai-workflow set-review … --review-context …` cannot publish a report whose
provenance claims an enforced boundary it does not have. The correct behavior is
to report the run as unsupported/blocked and escalate — never an automatic
permission weakening, never a model-session retry, and never a passing isolated
verdict from a session that could not demonstrate denial.

The one host profile that *is* demonstrated is the WSL bubblewrap boundary
recorded in [../local-review.md](../local-review.md); that document, not this
runbook, is the evidence source for support claims.

## Step 0 — cost-free diagnostics (no model session)

Collect these first; they consume no model budget:

```bash
codex --version        # pilot observed: codex-cli 0.160.0
codex exec --help      # the installed build's actual flags
```

Read the installed `codex exec --help` output **before using any flag**: this
runbook's flags are only valid where your installed help lists them (for the
observed build: `-c/--config <key=value>` overrides and the
`-s/--sandbox <read-only|workspace-write|danger-full-access>` policy). A
config key your build's help does not support must be treated as unverified on
that build — do not copy the pilot's key blindly.

Version/help inspection is cost-free and **does not authorize a model
session**.

## Distinguish launch/policy rejection from model findings

- **Launch/policy rejection**: every invocation is rejected before any work
  happens (metadata empty, no commands executed, no verification possible).
  In the pilot, session #7's output was inconclusive for exactly this reason
  and was superseded. A policy rejection says **nothing** about the change
  under review — it is not a technical verdict and never becomes one.
- **Model findings**: produced only by a session whose commands actually ran.

Never interpret the text of a policy-blocked session (its partial `review.md`
or console output) as review findings. Log interpretation comes after a
successful bounded diagnostic, never before.

## Bounded read-only diagnostic (separately budgeted; implementation-time validation only)

Before interpreting any review logs from a Windows `codex` run, a **successful
bounded read-only diagnostic** must exist on that host:

- It is a **separately budgeted** live smoke session — authorized at execution
  time as implementation-time validation, never implied by planning or by this
  document.
- Its prompt performs **one read-only repository command** (for example a
  status/read-only listing) and nothing else, and must **report a policy
  refusal separately** from command output — a refusal is surfaced as a
  launch failure, never folded into the command's result.
- Launch preference on Windows, matching the pilot's observed read-only
  posture, is the per-session setting shown above (after confirming your
  installed help supports it). Keep the session read-only and bounded.

A diagnostic that completes its one read-only command establishes that the
harness launches on that host. It establishes nothing about any ticket.

## Stop conditions (non-negotiable)

On any launch/policy rejection: **stop**. Specifically:

- no automatic retries and no retry loops — the pilot's flag was found by a
  budgeted, human-directed probe series, not by automatic re-launching;
- no edits to global or user configuration (no `~/.codex/config.toml`
  changes, no persistent config writes) — the observed fix is per session;
- no sandbox downgrade or permission weakening — never trade up to
  `workspace-write`, `danger-full-access`, or any bypass flag to "make it
  work"; current permissions are preserved exactly;
- report the rejection (with the version/help output collected in Step 0) and
  hand the decision back to the operator.

A successful launch changes none of this: it proves the harness starts, and the
isolated-review section above still says the session is unsupported until a host
write restriction is actually demonstrated.
