# Windows / WSL launch repair validation

Date: 2026-10-10 UTC. Baseline: `3aa9fc6700ad89485cdde1a7d8f993ac3754bcf2`.
Branch: `fix/windows-wsl-launch-utf8` in the separate local clone
`C:\Users\Kevin\Documents\Codex\2026-10-10\task\agent-workflow-fix`.
The source `D:\Code\agent-workflow` and its existing untracked research note
were not edited. No push, PR, merge, installation or security change was made.

## Change and review

`host_runtime.py` resolves the process platform and actual WSL2 distro, translates
drive paths with that distro's `wslpath`, and routes WSL UNC roots before command
dispatch. Both UNC server spellings work. A global `--repo` permits a Windows
launcher to select a WSL root while loading the kit from a readable local drive.
Verifier arguments after `--` are preserved. Unsupported shares, device paths,
drive-relative roots/outputs, WSL1, absent Linux Python and conflicting distro
overrides are refused with named startup diagnostics.

New context manifests pin the coordinator platform and actual distro. Currentness
checks reject a changed coordinator before running/publishing. Legacy manifests
retain their exact live-root and raw-byte identity checks; no context migration
or artifact transcoding is introduced. CLI stdout/stderr are UTF-8 and test CLI
callers explicitly decode UTF-8. Captured verifier bytes remain binary.

An independent read-only reviewer identified init target translation with
`--with-skills` before the target and normalization hiding drive-relative paths.
Both had failing regressions before repair and passed afterward; the reviewer
confirmed those findings closed. Distro override matching was also made
case-insensitive against the canonical observed distro name.

A final real read-only probe found that WSL `--cd /nonexistent` reports a chdir
error yet starts Python from `/` and exits 0. The handoff now passes an explicit
POSIX `--repo` to the Linux CLI instead, which validates/chdirs before dispatch.
Its failing regression passed after the fix; an empty UNC invocation keeps the
native help behavior. Independent followup review found no must-fix issue.

## Automated regression results

The final implementation commit `92912a7068cd0cbb11fb9275fcf8ff5eca5c41db`
passed full discovery on both hosts. Each run used its own private TEMP/TMP/TMPDIR,
so WSL index-cleanup tests could not observe another suite's temporary files.
The runner checked the exact commit and clean checkout before and after each run.
The Git cleanliness check used command-local `-c core.autocrlf=true` to match the
Windows checkout; it changed no config or file bytes. Temporary directories were
removed after successful completion.

| Final host | Total | Passed | Failures | Errors | Skipped | Seconds | Exit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Windows Python 3.13.5 | 509 | 505 | 0 | 0 | 4 | 1354.248 | 0 |
| WSL Ubuntu-24.04 Python 3.12.3 | 509 | 509 | 0 | 0 | 0 | 1025.293 | 0 |

Windows ran from 02:53:39 to 03:16:14 UTC; WSL from 02:53:43 to 03:10:52 UTC.
The raw logs and machine-readable summaries are in parent workspace
`final-commit-regressions/reconnected/windows.log`, `windows-summary.json`,
`wsl.log`, and `wsl-summary.json`. Raw log SHA-256 values:

- Windows: `5889aa24644d65f6178eb6464f48a023831fa0f633be00663b2803d21d3aef7b`
- WSL: `e1d2d6f2f08ae462c72b6c7a414b9d32071d1f1224258ceb9591339786a32eb5`

The four existing Windows skips require unavailable symlink privileges:
`test_artifact_archive.ArtifactArchiveTest.test_reject_unsafe_member_symlink_outside_root`,
`test_plan_v2.PlanV2Test.test_symlink_escape_rejected`,
`test_review_snapshot.ReviewSnapshotTest.test_directory_symlinks_are_classified_not_followed`,
and `test_review_snapshot.ReviewSnapshotTest.test_unsafe_input_scopes_reject`.
No skip or test assertion was added to accommodate this repair.

The first final-commit attempts lost the execution-server connection at about
02:33 UTC. Their logs stopped mid-suite, with no footer or summary; they count as
interrupted runs, not passing or failing tests. After reconnection, both original
sessions and their Python processes were confirmed absent before replacement
runs started. The interrupted logs remain at `final-commit-regressions/windows.log`
and `wsl.log`; only the completed replacement runs above are final results.

Historical checks, before the final missing-root guard:

| Verification | Result | Log in parent workspace `test-logs/` |
| --- | --- | --- |
| WSL full suite before the final missing-root guard | 506 tests, 1043.975 s, OK, zero skips | final-wsl.log |
| Windows full suite started before that guard | 506 tests, 1426.628 s, OK, four existing symlink-privilege skips | final-windows.log |
| Windows snapshot regression | 17 tests, OK, two existing symlink-privilege skips | snapshot-windows.log |
| Windows CLI parser regression | 10 tests, OK | main-final.log |
| Existing index cleanup regression, private Windows temp | 1 test, 0.996 s, OK | isolated-index-windows.log |
| Existing index cleanup regression, private WSL temp | 1 test, 0.973 s, OK | isolated-index-wsl.log |

After the last two-line routing change and its three new regressions, the latest
code passed all startup/encoding/parser tests on both hosts: Windows 27 tests
in 0.666 s, WSL 27 tests in 2.198 s (zero skips), logged in parent workspace
`post-cd-guard/focused-windows.log` and `focused-wsl.log`. The historical 506-test
counts are separate from the final 509-test full runs above. The latest real
three-route checks below were also repeated after the guard.

The earlier Windows full run (before the final review regressions) also passed:
500 tests, 1442.890 s, OK with four existing Windows symlink-privilege skips
(`full-windows.log`). No new skips were added.

The complete suite is invoked with:

```text
python -m unittest discover -s scripts/ai-workflow/tests -v
wsl.exe -d Ubuntu-24.04 --cd /mnt/c/Users/Kevin/Documents/Codex/2026-10-10/task/agent-workflow-fix --exec python3 -m unittest discover -s scripts/ai-workflow/tests -v
```

The new routing tests simulate discovery/launch seams and are not isolation
evidence. UTF-8 tests launch actual CLI subprocesses with legacy
`PYTHONIOENCODING=cp1252` and `PYTHONUTF8=0`; Chinese success/error messages are
strictly decoded as UTF-8. Context tests cover platform/distro mismatch and legacy
identity. Existing lifecycle/publication tests can use their fixture supervisor;
their pass alone does not establish host isolation.

An earlier overlapping WSL full run executed 500 tests and failed the existing
`test_unreadable_index_is_a_contract_error` global temp-directory assertion. Its
before/after sets showed one foreign directory disappear and another appear while
the final suite ran concurrently. The test scans all `/tmp/ai-workflow-index-*`
directories, rather than just its own invocation. No assertion, skip or production
cleanup was changed to hide that observation. Final and isolated rerun results
are retained separately in the table and logs. The final WSL full suite passed
the same test without overlap with another WSL full suite at that point.

## Actual host validation

Windows 11 AMD64, Windows Python 3.13.5, WSL2 Ubuntu-24.04, Linux Python 3.12.3,
kernel `6.6.87.2-microsoft-standard-WSL2`, existing bubblewrap 0.9.0.

The workspace helper `verify_launch_routes.py` seeds disposable valid v2 tickets
and uses the actual CLI and boundary. It uses the test helper only for fixture
content setup; no boundary launcher or supervisor is substituted. Each repository,
context and registered plan includes Chinese characters and spaces.
All three routes were repeated after the final missing-root guard; the latest
results are in `post-cd-guard/`, with the earlier evidence retained separately.

| Invocation | Coordinator recorded | Actual result |
| --- | --- | --- |
| Windows Python, local-drive root | win32 / Ubuntu-24.04 | prepare, baseline, probe, raw capture, guarded publication passed |
| Windows local kit, `--repo \\wsl$\Ubuntu-24.04\...` | linux / Ubuntu-24.04 | whole CLI entered WSL before prepare; same checks passed |
| Linux Python inside WSL | linux / Ubuntu-24.04 | native prepare/run/publication checks passed |

All three recorded `profile=linux-bwrap-v1`, `enforced=true`,
`network_denial_errno=101`, `meta_mounted=false`, and sentinel cleanup. Verifier
shell metacharacters remained argv data. A probe exit of 7 was returned by the CLI
and persisted in the real receipt. A verifier emitting stdout `00ff0d0a` and
stderr `fe000a` retained exactly those raw bytes and matching hashes. Live protected
artifacts and Git index bytes stayed unchanged during verifier execution.

`\\wsl.localhost` reused the UNC route's prepared context successfully. Switching
the Windows local context to a Linux coordinator failed with
`review-context-runtime-mismatch`. Missing/conflicting distro overrides were
refused without adding receipts or changing protected bytes. A real UNC-routed
`init --with-skills <Chinese Windows drive target>` installed all eight skills in
the intended target. Guarded publication on all three routes preserved candidate
review/handoff bytes; these disposable `changes_requested` fixture verdicts test
transport/publication, not the technical verdict for this repair.
A real Windows `--repo` pointing to a missing Chinese/space WSL path returned 1
with UTF-8 `cannot open repository`, before `init`; it created no missing root.
See `post-cd-guard/missing-unc-evidence.json`.

Evidence is retained in the parent workspace:

- `windows-local-evidence.json`, `windows-unc-evidence.json`, `wsl-native-evidence.json`
- each route's `*-extra.json` (raw binary capture and distro refusal)
- each route's `*-publication.json` (raw candidate publication hashes)
- `unc-init-target.log` and `verify_launch_routes.py`
- `validation-evidence/<route>/meta` (raw manifests, preflights, receipts, captures
  and publication journals), `scratch`, and `live_artifacts`

These are raw evidence exports, not replayable contexts: repository snapshots are
not copied and original absolute root identities are retained.
`validation-evidence/SHA256SUMS.json` inventories the 81 exported files by raw
SHA-256 and byte length; its creation did not rewrite those files.
The latest post-guard evidence has its own 81-file inventory at
`post-cd-guard/validation-evidence/SHA256SUMS.json`.

## Changed files

- Runtime: `scripts/ai-workflow/host_runtime.py`, `main.py`,
  `review_boundary.py`, `review_snapshot.py`.
- Regressions/caller decoding under `scripts/ai-workflow/tests/`:
  `test_host_runtime.py`, `test_cli_utf8.py`, `test_main.py`,
  `test_review_snapshot.py`, `test_dogfood.py`, `v2_support.py`.
- Documentation: `README.md`, `adapters/local-review.md`,
  `.scratch/windows-wsl-launch/spec.md`, this validation record.

## Delivery and source preservation

The implementation is commit `92912a7068cd0cbb11fb9275fcf8ff5eca5c41db` on
`fix/windows-wsl-launch-utf8`. This final validation update is a documentation-only
followup. The tested `scripts/ai-workflow` tree is
`115a4ae089419e711b2638addcecf5f1fafaa269`; the `.ai/workflow` tree is
`936b401028c9acf61a1a85184e33ca517bf70393`.

Read-only before/after audits are retained as
`final-commit-regressions/source-before.json` and `source-after.json` in the parent
workspace. At 03:19:01 UTC the original checkout still had baseline HEAD on
`master`, and only the original untracked research note. Its SHA-256 remained
`878f47c259a4ec38033b44eba620217c70a65b6909f04b65f3cce75d42c7443d`;
the Git index raw-byte SHA-256 remained
`9de6f43bdb38872c15b7046bd4ecd04f8323984515f240a8400cac1c8228a717`.

The combined implementation and validation mailbox patch is exported as
`agent-workflow-windows-wsl-verified.patch` in the parent workspace. The following
are optional manual adoption commands, provided for review and **not executed**:

```powershell
git -C D:\Code\agent-workflow switch -c fix/windows-wsl-launch-utf8
git -C D:\Code\agent-workflow am "C:\Users\Kevin\Documents\Codex\2026-10-10\task\agent-workflow-windows-wsl-verified.patch"
```

## Limits and remaining items

The Windows execution token cannot read either UNC server: native Python loading
a UNC script and opening an UNC cwd was blocked before kit code runs. The explicit
`--repo` Windows-to-UNC route was actually exercised. Automatic UNC cwd/script
routing is covered by simulated argv/path tests; direct native access could not
be verified on this host without a host permission change, which was not made.

Only the installed Ubuntu-24.04 WSL2 distro was used; a successful second-distro
switch was not tested. Conflicts and unavailable distro errors were exercised.
Prepare validates startup/runtime/path compatibility; actual bwrap namespace and
write restrictions are established by run-review preflight. The GitHub CI bwrap
startup issue remains outside this repair, as requested.

Bubblewrap (`bwrap`) is the Linux isolation launcher for the verifier: it sets up
filesystem mounts and process/network namespaces so review commands can write
their snapshot/scratch while protected live data stays read-only.
