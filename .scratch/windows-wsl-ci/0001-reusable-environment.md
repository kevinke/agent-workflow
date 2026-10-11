# 0001: Reuse a pinned clean WSL2 environment in Windows CI

Status: implemented locally; local full suite and hosted validation pending.

Acceptance: Windows Python remains the full-suite coordinator, a new dedicated
WSL2 Ubuntu runtime passes production isolation preflight, cold bootstrap and
exact cache restore are observable, no workspace/credential bytes enter the
cache, and failures preserve diagnostics without relaxing production policy.

Implemented: official rootfs/SHA and fixed signed APT snapshot, non-root CI
user, definition/script cache key, raw tar digest and sensitive-path validation,
pre-test export, version diagnostics, strict boundary gate, and evidence upload.

Independent review found two cold-export blockers (relative system symlinks
and WSL's generated resolver link). Both were reproduced and corrected with
tar regressions; focused re-review found no remaining important issue.

Local evidence so far: 11 Windows tar/provenance regressions pass; initial 9
also passed with WSL Linux Python. Existing Ubuntu-24.04 on WSL2 passes real
review_boundary.preflight from Windows Python. Local bootstrap refuses before
any WSL mutation outside an ephemeral GitHub job. No local software was installed.

Local full suite completed: 518 collected cases, 0 failures/errors, 4 existing
Windows symlink skips. Final additions were checked separately on both runtimes.

First hosted run: master b51a2bd, run 38112185528. Ubuntu passed 521 cases with
its existing 4 bwrap skips. Windows successfully imported WSL2 and installed
packages, then failed cleaning the readonly WSLg X11 mount. The repair preserves
that mount and allows only its empty directory in the cache; 13 focused cases
pass on both runtimes and a real readonly-mount cleanup regression passes.
Targeted independent review found no important issue. Package sources now use
the direct dated snapshot URL so update cannot also read live archive indexes.

Remaining verification: real hosted cold build,
non-root import, boundary, full suite and clean cache restore. User authorized
normal master push and CI on 2026-10-11. Preserve existing source changes.
