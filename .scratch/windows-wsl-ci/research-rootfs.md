# Canonical WSL rootfs and APT snapshot research

Status: researched locally on 2026-10-11. Scope: official Ubuntu sources, no distro installation, package installation, host configuration changes, remote writes, or CI runs.

## Usable fixed official base

Use the AMD64 Noble **release** rootfs in the dated `20240423` directory, with a committed expected digest. Both the dated image and its signed checksum listing are currently published by Canonical. This fixes the base filesystem bytes; neither the `Ubuntu-24.04` install alias nor a `current/` URL is a byte-level pin. [Release directory](https://cloud-images.ubuntu.com/wsl/releases/noble/20240423/), [published checksums](https://cloud-images.ubuntu.com/wsl/releases/noble/20240423/SHA256SUMS).

```text
URL=https://cloud-images.ubuntu.com/wsl/releases/noble/20240423/ubuntu-noble-wsl-amd64-wsl.rootfs.tar.gz
SHA256=8251e27ffff381a4af5f41dcb94d867de3e0d9774a9241908ab34555d99315ea
SUMS=https://cloud-images.ubuntu.com/wsl/releases/noble/20240423/SHA256SUMS
SIGNATURE=https://cloud-images.ubuntu.com/wsl/releases/noble/20240423/SHA256SUMS.gpg
SIGNING_FINGERPRINT=D2EB44626FDDC30B513D5BB71A5D6C4C7DB87C81
```

The same directory also contains `ubuntu-noble-wsl-amd64-24.04lts.rootfs.tar.gz`, which has a **different** digest, `2a790896740b14d637dbdc583cce1ba081ac53b9e9cdb46dc09a2f73abbd9934`. Match filename and digest exactly; do not interchange them. [Published checksums](https://cloud-images.ubuntu.com/wsl/releases/noble/20240423/SHA256SUMS).

The base manifest includes `python3.12` / its libraries at upstream 3.12.3, APT 2.7.14build2 and Git 1:2.43.0-1ubuntu7. This is an older base, so configure a newer fixed package snapshot for the bootstrap additions/updates. [Package manifest](https://cloud-images.ubuntu.com/wsl/releases/noble/20240423/ubuntu-noble-wsl-amd64-wsl.manifest).

Prefer a release directory over a daily serial: Canonical documents deletion of older daily serials, while active LTS release images are retained. Still fail clearly if the pinned download becomes unavailable; do not silently substitute another image or digest. [Image retention policy](https://ubuntu.com/docs/public-images/public-images-explanation/public-image-retention-policy/).

## Checksum authentication

Canonical's cloud-image verification guide identifies the UEC signing fingerprint above and describes verifying `SHA256SUMS.gpg` against `SHA256SUMS`, then checking downloaded image bytes. This cloud-image signer differs from the CD-image signer commonly shown in ISO verification guides. [Official cloud-image verification](https://ubuntu.com/docs/public-images/public-images-how-to/verify-image-checksum/).

Actual local evidence: downloaded only the tiny checksum/signature/public-key files, inspected the signature, and verified them using the already-installed Git GnuPG and a dedicated temporary keyring. The key came from `https://keyserver.ubuntu.com/pks/lookup?op=get&search=0xD2EB44626FDDC30B513D5BB71A5D6C4C7DB87C81`; its full fingerprint matched the official documentation. Final signature verification exited **0** and reported:

```text
GOODSIG 1A5D6C4C7DB87C81 UEC Image Automatic Signing Key
VALIDSIG D2EB44626FDDC30B513D5BB71A5D6C4C7DB87C81
signature date: 2024-04-24
```

The temporary key import emitted a Git GnuPG agent warning; the independent final public-signature verification nevertheless returned the exact `VALIDSIG` and exit 0. No private key, user keyring or WSL distro was changed. The large rootfs itself was **not downloaded or hashed** in this research task.

For bootstrap, compare `Get-FileHash -Algorithm SHA256` with the reviewed, committed expected digest before import and on cache restore. Signature verification is appropriate when refreshing the committed pin; fetching a checksum dynamically and accepting its contents without an authenticated signer would weaken the pin. This recommendation follows the documented signature-then-image validation chain. [Ubuntu integrity verification](https://documentation.ubuntu.com/security/software-integrity/image-verification/).

## Fixed package resolution

Cold-bootstrap compatibility was checked against the **exact Ubuntu 2.7.14build2 source**, rather than relying on the currently published Noble manpage (which identifies APT 2.8.3). Downloaded the inert [official source archive](https://archive.ubuntu.com/ubuntu/pool/main/a/apt/apt_2.7.14build2.tar.xz) and read selected members in memory without extraction, building or installation. Its SHA256 was `7d4d0f2eb95464d175ef6a09b2b8f7040f56a8de77fa3b73de52d80395428410`, matching the [official DSC checksum](https://archive.ubuntu.com/ubuntu/pool/main/a/apt/apt_2.7.14build2.dsc). The archive's internal directory happens to be named `apt-2.7.14build1`; the downloaded filename and matching DSC identify the packaged 2.7.14build2 source.

Evidence within that archive:

- `apt-private/private-cmndline.cc:275` registers `-S` / `--snapshot` as an argument mapped to `APT::Snapshot`.
- `doc/apt-get.8.xml:542-548` documents `apt-get --snapshot`.
- `doc/sources.list.5.xml:397-411` documents the Deb822 `Snapshot` field accepting a specific timestamp.
- `apt-pkg/deb/debmetaindex.cc:1304` reads the source's snapshot option; `:1421` applies it to the index.
- `debian/changelog` records initial snapshot support in **2.7.0**, known-host snapshot-server seeding in **2.7.1**, and automatic enabling in **2.7.12**.

Therefore, the pinned rootfs's **2.7.14build2 supports the first `apt-get update --snapshot` and explicit source timestamp**. Upgrading APT first, using a live repository for bootstrap, or changing to a direct snapshot URI is unnecessary for this compatibility concern. This is source-level verification; an actual transaction in the imported rootfs remains untested here.

Ubuntu's official snapshot service supports Noble and UTC snapshot IDs. It intends to retain timestamps for at least two years, rather than promising permanent availability. Noble supports snapshots without a custom package repository or credentials. [Ubuntu Snapshot Service](https://snapshot.ubuntu.com/).

Proposed snapshot: **20261001T000000Z**. Actual HTTP reads of these official files all returned **200**:

| Suite | Metadata date | Expiry field |
|---|---|---|
| [noble](https://snapshot.ubuntu.com/ubuntu/20261001T000000Z/dists/noble/InRelease) | 2024-04-25 15:10:33 UTC | No `Valid-Until` |
| [noble-updates](https://snapshot.ubuntu.com/ubuntu/20261001T000000Z/dists/noble-updates/InRelease) | 2026-09-30 22:15:24 UTC | No `Valid-Until` |
| [noble-security](https://snapshot.ubuntu.com/ubuntu/20261001T000000Z/dists/noble-security/InRelease) | 2026-09-30 16:40:42 UTC | No `Valid-Until` |

APT accepts a specific `Snapshot:` value in Deb822 sources; `Signed-By` selects the Ubuntu archive keyring. The explicit value prevents accidentally resolving against the current archive. Keep normal signature, date and expiry checks enabled. No validity-check bypass is indicated by the metadata above. [Noble sources.list manual](https://manpages.ubuntu.com/manpages/noble/man5/sources.list.5.html).

In a **fresh disposable CI distro only**, use these two source stanzas as its complete Ubuntu source configuration (do not retain extra unpinned sources):

```text
Types: deb
URIs: https://archive.ubuntu.com/ubuntu
Suites: noble noble-updates
Components: main universe
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
Snapshot: 20261001T000000Z

Types: deb
URIs: https://security.ubuntu.com/ubuntu
Suites: noble-security
Components: main universe
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
Snapshot: 20261001T000000Z
```

APT also documents `--snapshot` / `-S`, strict update error handling, and normal authenticated package installation. After writing the pinned source configuration, a minimal CI bootstrap recipe is:

```sh
apt-get update --error-on=any --snapshot 20261001T000000Z
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  --snapshot 20261001T000000Z python3 git bubblewrap ca-certificates
dpkg-query -W -f='${Package}\t${Version}\n'
```

An optional whole-base update would use `apt-get dist-upgrade -y --snapshot 20261001T000000Z` after the same strict update. It is broader than the minimal dependency bootstrap and can remove packages. Do not add `--allow-unauthenticated`, insecure repository options, disabled date checks, or disabled expiry checks. [Noble apt-get manual](https://manpages.ubuntu.com/manpages/noble/man8/apt-get.8.html).

The recipe has **not been run** in an imported distro here; package candidate versions, actual package fetches, bootstrap/export/import duration and isolated execution still require implementation validation. Metadata availability alone is not proof of a successful APT transaction. Record package versions on rebuild, and fail if the fixed snapshot disappears rather than falling back to live repositories.

## Reuse boundary

Actual implementation finding from CI run 38112185528 on 2026-10-11: APT 2.7.14
supports the snapshot options, but `update --snapshot` with live archive URIs
reads both live and selected snapshot indexes. Package installation used the
snapshot. To remove the unnecessary live inputs entirely, the implementation
now configures only `https://snapshot.ubuntu.com/ubuntu/20261001T000000Z/`
as the URI for noble, noble-updates and noble-security, with the same Ubuntu
archive Signed-By keyring and normal signature/date/expiry checks. No Snapshot
field or command-line option is needed for this directly dated repository.

Implementation recommendation: commit the URL/digest, snapshot, package list and provisioning script; derive the cache key from this environment definition; build a clean distro with no checkout/credentials inside it; export before test execution; import the same clean tar on cache hits. Rebuild on cache loss using the exact definition. Changing a definition requires a new cache key.

The rootfs and snapshot pin Linux userland inputs. They do not pin the Windows host, WSL executable, WSL kernel or runner image; record all of those alongside each run. This boundary is a design inference from the separation between the filesystem tar and the WSL host, not a claim of complete machine reproducibility.
