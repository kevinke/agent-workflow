# Local isolated-review boundary — `linux-bwrap-v1` (adapter guidance)

This documents the one host arrangement in which an **isolated reviewer
verification** is actually demonstrated on this project: a Windows coordinator
that drives `bwrap` inside WSL. It is adapter guidance only — it adds no workflow
rule, no permission and no global configuration. The procedure and its limits
live in `.ai/workflow/PROTOCOL.md` §"Reviewer verification isolation and
publication"; the report's provenance contract lives in
`.ai/workflow/ARTIFACTS.md` §"Verification provenance for new isolated reviews".

## What supported means here

Supported means: every verifier command the reviewer runs executes inside a real
kernel-enforced mount namespace that cannot write the live tree, **and** that
denial was observed on this host by this project's own entry point
(`ai-workflow run-review`), not asserted by a test helper, a prompt or a config
file. Helper/mocked tests never establish adapter support; a Harness host
restriction is only what the host actually enforces.

## Usage

```
ai-workflow prepare-review <ticket-id> --commit <literal-oid> --output <new-directory>
ai-workflow run-review <ticket-id> --review-context <new-directory> --kind baseline -- <argv...>
ai-workflow run-review <ticket-id> --review-context <new-directory> --kind probe -- <argv...>
ai-workflow set-review <ticket-id> --verdict <pass|changes_requested> \
    --review-context <new-directory> --report <new-directory>/scratch/review.md \
    --handoff <new-directory>/scratch/handoff.md
```

The prepared context is `repo/` (the disposable clone of the reviewed commit, the
verifier's `/snapshot` and its working directory), `scratch/` (candidate report,
candidate handoff and any verifier output) and `meta/` (supervisor-owned manifest,
preflight evidence, receipts and publication journal). A publication consumes its
context: each verdict needs its own prepared context.

## Measured evidence on this host

Recorded from the boundary's own runs on the machine this kit is developed on.
Where the measurement lives, resolvable from a fresh checkout of this
repository (nothing below points at a git-ignored working note):

- `scripts/ai-workflow/tests/test_review_boundary.py` (`ReviewBoundaryTest`)
  drives the same `bwrap` code path `run-review` uses and asserts the denial
  table, the writable scopes and the network refusal;
  `scripts/ai-workflow/tests/test_review_publication.py`
  (`ReviewPublicationTest`) asserts that guarded publication validates those
  receipts field by field; and
  `scripts/ai-workflow/tests/test_lifecycle_v2.py`
  (`InstalledIsolatedReviewLifecycleTest.test_installed_isolated_review_lifecycle`)
  drives the installed kit end to end and records which route produced its
  receipts.
- The fields the supervisor itself writes into a prepared context carry the same
  measurement for any real run. `meta/preflight.json` records `profile`,
  `enforced`, `blocker`, `bwrap_version`, `supervisor_host`, `sandbox_host`,
  `launcher`, `distro`, `cwd`, `env_keys`, `mount_roots`, `denials`,
  `rename_errno`, `writable`, `not_visible`, `network_denied`,
  `network_denial_errno` and the `sentinel` re-enumeration. Each
  `meta/runs/<run_id>.json` receipt records `kind`, `argv`, `cwd`, `exit_code`,
  `stdout_sha256`, `stderr_sha256`, `snapshot_before`, `snapshot_after`, the
  residual snapshot changes as `changed_paths`/`added_paths`/`removed_paths`, and
  a `boundary` summary of that evidence (`denials_attempted`, `denial_errnos`,
  `network_denial_errno`, `env_keys`, `sentinel_removed`).

The values those sources recorded here:

- **Host.** Windows coordinator (native Python) launching `wsl.exe -d
  Ubuntu-24.04 --exec` → installed `bwrap`, **bubblewrap 0.9.0**. Reviewer argv is
  passed after a literal `--exec`, never re-parsed by a login shell.
- **Global flags, always.** `--unshare-all --new-session --die-with-parent
  --clearenv`; stdin `DEVNULL`, descriptors closed, captured streams written 0600.
- **Mount set (allowlisted; anything else is the named blocker
  `unapproved-mount-root`).** `--tmpfs /`; `--dev /dev`; `--proc /proc`;
  `--ro-bind /usr /usr`; usr-merge `--symlink` for `/bin`, `/lib`, `/lib64`,
  `/sbin`; `--tmpfs /tmp`; `--bind <context>/repo /snapshot`;
  `--bind <context>/scratch /scratch`. Environment is rebuilt from an allowlist of
  `HOME`, `LC_CTYPE`, `PATH`, `PWD` only (`HOME=/tmp`).
- **`/live` exists only during preflight.** `preflight` builds its own disposable
  protected sentinel (a source file, a test file, a fixture, a config file and a
  fake `.git/index`) under the supervisor's `meta/`, mounts it
  `--ro-bind … /live`, and removes it afterwards. A **verifier run mounts no live
  path at all**, and `meta/` is never mounted into any sandbox.
- **Observed denials.** Every write attempt against `/live` was refused as a
  privilege denial on the read-only bind — **`EROFS`** for overwrite, append,
  truncate, unlink and new-file creation, including against the fake `.git/index`;
  `mkdir`/`makedirs` and `chmod` likewise refused; cross-mount escapes out of
  `/live` into `/snapshot`, `/scratch` and `/tmp` refused with **`EXDEV`** (rename)
  and the same refusal for the hard-link attempt. The supervisor then
  re-enumerates the sentinel from the host side and requires the file set, bytes
  and modes to be **unchanged**; a sandbox that lies about a denial fails
  `protected-sentinel-changed` / `boundary-denial-unverified`.
- **Observed allowances.** `/snapshot`, `/scratch`, `/tmp` and `$HOME` all proved
  writable from inside the same sandboxed process (the four `WRITABLE_SCOPES`);
  probe edits inside `/snapshot` are recorded, not blocked.
- **Reachability.** `/meta`, `/mnt`, `/mnt/c`, `/run`, `/home`, `/init` and the X11
  sockets do not exist inside the boundary, so neither the supervisor's records nor
  the live Windows tree nor WSL interoperability is reachable.
- **Network.** `--unshare-all` leaves no interface: the measured refusal is
  **`ENETUNREACH`**, recorded as the Linux literal `101`. Windows' own
  `errno.ENETUNREACH` is WSA `10051`, so the profile grades Linux values and docs
  must never quote the supervisor platform's number. A timeout, `ECONNREFUSED`,
  `ECONNRESET` or `EHOSTUNREACH` is *not* accepted as a no-network proof, because
  each is also what a boundary with a network produces.
- **Inherited environment.** No inherited `GIT_*` override survives `--clearenv`
  (an unsanitized `GIT_DIR`/`GIT_WORK_TREE`/`GIT_INDEX_FILE`/`GIT_CONFIG*` is the
  named blocker `inherited-environment-not-cleared`), and the in-sandbox probe must
  report `cwd == /snapshot` before the boundary is trusted.
- **Real runs, measured on this host (2026-10-10).** A prepared context published
  through the installed-lifecycle path recorded, for **both** verdicts,
  `profile=linux-bwrap-v1 enforced=true blocker=None`,
  `supervisor_host="Windows 11 (AMD64)"`,
  `sandbox_host="Linux 6.6.87.2-microsoft-standard-WSL2"`,
  `bwrap_version="bubblewrap 0.9.0"`, `cwd=/snapshot`, `meta_mounted=false`,
  `network_denial_errno=101` and `env_keys=["HOME","LC_CTYPE","PATH","PWD"]`.
  Thirty sentinel attempts were recorded and all thirty were denied: **`EROFS`
  (30)** for `open-write`, `open-append`, `open-truncate`, `unlink`, `mkdir`,
  `chmod`, `symlink` and new-file creation — including against
  `/live/.git/index` — and **`EXDEV` (18)** for the three cross-mount `rename`
  attempts and the cross-mount hard `link`. `/snapshot`, `/scratch`, `/tmp` and
  `$HOME` were all writable, the supervisor's re-enumeration found every sentinel
  file's bytes, size and mode unchanged, and `sentinel.removed` was true. The
  boundary legs of `test_review_boundary` and the guarded publication suite run
  with 0 skips against this host, and the installed isolated-review lifecycle
  records which route produced its receipts (`linux-bwrap-v1 on this host` here;
  otherwise its documented fixture supervisor, which is never a support claim).
- **Host traps carried into the implementation.** Windows paths are translated
  explicitly (`C:\x` → `/mnt/c/x`) because `wsl.exe` receives them verbatim from
  native Python; and a `core.autocrlf` Windows checkout reads as modified to Linux
  Git inside the sandbox, so every receipt identity is built from supervisor-side
  raw byte hashes, never from in-sandbox `git status`.

## Limits of what this proves (stated, not smoothed over)

- The **coordinator and publisher are trusted.** This boundary confines a
  reviewer's verifier processes; it is not authentication and not a defense
  against a malicious or careless coordinator.
- Support belongs to the **profile plus the host**, measured per run. An
  unconstrained outer reviewer that merely sandboxes its own tests, or a session
  whose harness has live write access, cannot claim support from this document.
- Publication is **journal-guarded recovery, not atomicity across three files**.
  The three records (Review, State, Handoff) plus the State commit marker are
  restored from the journal so a refused or interrupted publication leaves existing
  records and phase intact; the window in which a second, foreign writer edits a
  record it does not own is detected and refuses, and the journal is kept. There is
  **no operator-facing command to clear a journal-blocked context**: that context is
  discarded and a fresh snapshot plus a new independent review is the only route.
- Receipt agreement proves the recorded commands ran under the recorded mounts. It
  does not prove the review's technical judgment, that acceptance criteria passed,
  or the truth of the report's prose; structural validation establishes conformance
  only.
- Restoring probe bytes does not erase the execution record: baseline and probe
  runs are separate receipts, the first accepted baseline is pinned to the prepared
  snapshot identity, and residual snapshot changes stay in the report.
- The measured evidence is this host, this `bwrap` build, this WSL layout. Another
  host or build re-establishes it by running `run-review` there; the profile never
  weakens permissions to make a run succeed, and a blocker exits 1 with no receipt
  and no fallback to an unconstrained run.

## Not supported

- **Native Windows sessions** — no observed write restriction; see
  [codex/windows.md](codex/windows.md), which keeps the real launch diagnostics and
  states plainly that they prove nothing about live writes.
- **Codex Desktop / MCP sessions** — unsupported until that host's own tool-write
  restriction is separately demonstrated.
- On an unsupported host `run-review` reports a named blocker (typically
  `bwrap-executable-not-found` or `unsupported-runtime-layout`), `preflight`
  persists `enforced: false` with that blocker, and guarded publication refuses a
  provenance that claims enforcement it cannot back. The correct outcome is a
  reported blocker and no passing isolated verdict.
