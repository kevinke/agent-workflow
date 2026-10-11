# Windows / WSL launch and CLI UTF-8 repair

Status: implemented and verified; local delivery only

## Scope and evidence

Baseline: `master` at `3aa9fc6700ad89485cdde1a7d8f993ac3754bcf2`.
The source checkout is `D:\Code\agent-workflow`; its untracked research note
is preserved. Work happens in a separate local clone on
`fix/windows-wsl-launch-utf8`.

Windows Python previously prepared UNC review contexts with Windows `live_root`
strings. The boundary refused UNC mount sources, and a later Linux coordinator
refused the Windows root identity. Separately, `PYTHONIOENCODING=cp1252` caused
`init` to write protocol files and then raise `UnicodeEncodeError` when printing
a Chinese path. Chinese stderr diagnostics escaped rather than retained text.

## Bounded implementation plan

1. Reproduce legacy-encoding failures in real CLI subprocesses; pin Windows/WSL
   routing with focused tests, including distro conflicts and opaque verifier argv.
2. Route a Windows WSL UNC repository into its corresponding Linux Python before
   dispatch. Preserve Windows local-drive and native Linux coordinators. Resolve
   the actual WSL2 distro and mount translation explicitly. Pin new contexts to
   coordinator platform/distro, preserving existing raw-byte identity rules.
3. Fix CLI stdout/stderr UTF-8 and explicit caller decoding. Provide `--repo`
   before the command for Windows launchers unable to open UNC cwd themselves.
4. Run the complete Windows and WSL suites, plus actual prepare/run on all three
   routes in disposable Chinese/space paths. Distinguish seams, fixture supervisor
   coverage, real boundary receipts, and host-blocked direct UNC access.
5. Review the diff, document startup/decoding contracts and remaining limits,
   preserve a local commit and patch. Do not push or create a PR.

## Invariants

- No weakening of `linux-bwrap-v1`, no expanded skips, no isolation test doubles
  presented as host evidence; CI bwrap startup issues are out of scope.
- No transcoding of artifact, snapshot input, verifier capture or receipt bytes.
- No cross-platform/distro context migration; reprepare when the coordinator
  changes. Legacy contexts retain exact live-root and raw-byte checks.
- Unsupported paths/WSL2/Python environments fail with named diagnostics.
- No software installation, WSL enablement or security/permission changes.

## Local environment limitation

The current Windows execution token cannot read either WSL UNC server, even
after approved read-only diagnostics: loading a UNC `main.py` fails before its
code executes. Explicit `--repo <UNC>` with the kit on a local drive was added
and verified without changing that host permission. Direct UNC cwd/script access
is a separate host prerequisite; routing unit tests alone do not prove it.

## Comments

Execution logs and route evidence are retained beside the isolated checkout;
the final validation record identifies commands, counts, skips and limitations.
