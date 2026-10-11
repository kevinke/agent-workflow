# Reusable Windows / WSL2 CI environment

Local implementation and a normal push to master were authorized by the user
on 2026-10-11. Do not force push, replace developer distros, or relax isolation.

Use a standard windows-2025 hosted runner and Windows Python 3.13.5. Define
the Ubuntu 24.04 userland using a dated Canonical rootfs with a reviewed SHA256,
one signed APT snapshot, an explicit package list, and a bootstrap recipe.
Import a new dedicated WSL2 distro and use its non-root default user.

Prepare systemd=false and the cloud-init disabled marker before the first
guest boot, after original gzip hash verification. Keep opaque file payloads
and all other base entries unchanged; record the derived import tar hash.

Reuse only its clean export, captured before tests. Cache key includes every
environment-building input; validate definition, raw tar hash and sensitive
paths before import. Cache misses rebuild; missing upstream pins fail closed.
No checkout, user credentials or access tokens are put in the tar. Production
review_boundary.preflight must pass before the full Windows Python suite.

Record Windows runner image, Python, WSL, kernel, Ubuntu, package versions,
cache hit/rebuild and real boundary evidence in an uploaded artifact, including
on failure. Rootfs reuse does not freeze the hosted Windows/WSL/kernel. Do not
claim a permanent image or a successful hosted run before observing it.

Ubuntu CI's existing bwrap limitation is outside scope; retain its existing
test command and rules. No paid runner, self-hosted service or security-policy
change is part of this implementation.

Validation: tar/provenance unit regressions, local existing-distro production
preflight, full regression suite, code review, then exact-commit hosted CI.
Cold build, restore and package transactions run only on ephemeral hosted CI.
