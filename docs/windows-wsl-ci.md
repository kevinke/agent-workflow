# Windows / WSL2 CI environment

The Windows job starts the full regression suite with Windows Python 3.13.5.
It uses a dedicated WSL2 distro for the production Linux isolation boundary.
The definition is [.github/ci/wsl-environment.json](../.github/ci/wsl-environment.json),
with [bootstrap-wsl.sh](../scripts/ci/bootstrap-wsl.sh) and
[wsl_environment.py](../scripts/ci/wsl_environment.py).

The dated Canonical AMD64 Ubuntu 24.04 rootfs is checked against a committed
SHA256 before import. Signed packages resolve against the fixed
20261001T000000Z Ubuntu snapshot. Package signature/date verification remains
enabled. The bootstrap creates a non-root `ci` user and never replaces an
existing distro or changes the host's default distro. Refresh the digest only
after verifying Canonical's signed checksum listing; the research record is
[here](../.scratch/windows-wsl-ci/research-rootfs.md).

An exact cache key hashes the definition and both provisioning scripts. Only
the dedicated distro's pre-test export and provenance JSON enter the cache.
Before importing a hit, the helper checks the definition, raw tar digest, and
refuses workspace/credential paths. Only master push jobs save a cache, before
tests run; PRs can restore it. Checkout credentials are not persisted. No
workspace or private credentials are copied into the Linux rootfs.

The official base contains an empty `/root/.ssh`; bootstrap removes it using
`rmdir`, which fails if any content appears. Normal system links and the exact
WSL-generated resolver symlink are allowed, without caching mounted contents.

Each job still receives a new hosted Windows VM. `windows-2025` fixes its OS
family, not the complete runner image. WSL is updated on that disposable runner
and its actual version and kernel are recorded. The tar fixes Linux userland
inputs, not the Windows/WSL/kernel. Cache eviction causes a rebuild from the
same pinned inputs. GitHub caches and Ubuntu snapshots are not permanent
archives; a removed upstream pin produces a clear failure, never a live-archive
fallback. See [GitHub cache semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
and [Ubuntu snapshots](https://snapshot.ubuntu.com/).

Before any tests, the job executes `review_boundary.preflight` from Windows
Python against the selected WSL2 distro. Its actual production profile must
prove filesystem restrictions and network denial; fixture supervisors or
capability-only smoke tests cannot pass this gate. The `windows-wsl-evidence`
artifact (suffixed with the run attempt) includes environment diagnostics, actual package versions, cache
status, preflight evidence and full Windows suite output. The separate Ubuntu
job retains its existing behavior and existing skips.

Local read-only environment inspection (plus disposable preflight sentinels):

```powershell
python scripts/ci/wsl_environment.py plan
python scripts/ci/wsl_environment.py probe --distro Ubuntu-24.04 --diagnostics environment.json
```

`bootstrap` is restricted to ephemeral GitHub Windows jobs. It does not enable
Windows features, change security policy or install a distro on a developer's
computer. A runner without working WSL2 fails before testing. For the supported
tar format see [Microsoft custom distributions](https://learn.microsoft.com/en-us/windows/wsl/use-custom-distro).
