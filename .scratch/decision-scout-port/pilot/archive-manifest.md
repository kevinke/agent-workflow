# Pilot archive manifest — durable packages (HARDEN-006 Task 2)

The two historical pilot Tickets (`PILOT-BUG-01`, `PILOT-FEAT-01`) are
preserved as verified ZIP packages produced by the kit's
`artifact_archive.write_archive` (the publication primitive behind
`ai-workflow archive-artifacts`). Each ZIP holds the exact raw working bytes
of the archived ticket plus a `manifest.json` (`format_version: 1`). Nothing
in the original pilot target was checked out, edited, or re-gated; the
working bytes under `pilot/bug/` and `pilot/feature/` are the byte forms
already restored and verified against the recorded `state.yaml` bindings
(report.md, "Byte-level gate friction" section).

## Binding verification (performed before packaging)

All eight Evidence/Audit/Plan/Review hashes were verified against the
recorded values in each archived `state.yaml` FIRST; the packages below were
refused to be built from any recomputed replacement (the bytes are the
archived working bytes, not regenerated ones):

| Ticket | Member (working file) | Recorded in State | SHA-256 (verified match) |
|---|---|---|---|
| PILOT-BUG-01 | evidence.md | `evidence.report_sha256` | `71855e12d011d2d7345577633af211ae15e801b7e2b7e7056d8385dd9ab3a3f2` |
| PILOT-BUG-01 | evidence-audit.md | `evidence.audit_sha256` | `544977b162351a3a0114c079dc4904a29fdc736fe8141ed0fafaa9c12213439c` |
| PILOT-BUG-01 | plan.md | `review.plan_sha256` = `source_artifacts.plan.sha256` | `67a62c313ba78db8013d03b1a8dd1e804d44d9580cf2db04ad958ee33a0b152c` |
| PILOT-BUG-01 | review.md | `review.artifact_sha256` | `1421855eb96e3c3e2972f60a0d4ed6ea2d1d09317b604616f3cf74d70ba6c602` |
| PILOT-FEAT-01 | evidence.md | `evidence.report_sha256` | `930cd02b9275ddabc786d5d88ee170247f7fa905d4ba66fbc9590eb54dc46d4b` |
| PILOT-FEAT-01 | evidence-audit.md | `evidence.audit_sha256` | `8cc535552c3126e1ebdff44af49b3be9945de8d3d5178525015ae9d4447add9c` |
| PILOT-FEAT-01 | plan.md | `review.plan_sha256` = `source_artifacts.plan.sha256` | `349913c6bd74570f9bedeb18d652192b62bee358906b98bafa2cf0555f8a107d` |
| PILOT-FEAT-01 | review.md | `review.artifact_sha256` | `5e41b7510d4dc5df7b7aad0ea4d9f908ed41bfa459c23e3ba511bafd463451ec` |

## Original path mapping

Member paths inside each ZIP are the artifact's paths in the ORIGINAL pilot
target repository (taken from the archived State's `artifacts` names and
`source_artifacts.plan.path`); the right column is the pilot working file the
bytes were read from:

| ZIP member (original repo-relative path) | Pilot working file |
|---|---|
| `.ai/work/<TICKET>/state.yaml` | `<kind>/state.yaml` |
| `.ai/work/<TICKET>/evidence.md` | `<kind>/evidence.md` |
| `.ai/work/<TICKET>/evidence-audit.md` | `<kind>/evidence-audit.md` |
| `.ai/work/<TICKET>/decision.md` | `<kind>/decision.md` |
| `.ai/work/<TICKET>/progress.md` | `<kind>/progress.md` |
| `.ai/work/<TICKET>/handoff.md` | `<kind>/handoff.md` |
| `.ai/work/<TICKET>/review.md` | `<kind>/review.md` |
| `.scratch/<TICKET>/plan.md` | `<kind>/plan.md` |

with `<TICKET>` = `PILOT-BUG-01` / `PILOT-FEAT-01` and `<kind>` = `bug` /
`feature`. The registered Plan is packaged at its ACTUAL registered source
path (`.scratch/<TICKET>/plan.md`), not under an invented ticket-local copy.

## Snapshot heads (from recorded branch evidence)

`manifest.json.snapshot_head` values come from the pilot report's recorded
branch evidence (report.md, "What happened"): branch `pilot/bug` head
`a1cbdab` (the `done` commit) and branch `pilot/feat` head `aea68a6`. The
recorded review `reviewed_commit` values are `4a92d74a937acae0db7eb708e5c4943d839e89f7`
(bug) and `98a27205111380bbf401e5a0fd1296523d560594` (feature).

## Unbound supporting files (computed, never previously bound)

`decision.md`, `progress.md`, `handoff.md` and `state.yaml` carry computed
SHA-256 and a null `bound_sha256` in the manifests — the pilot States never
hash-bound them. Recorded here separately so the values are explicit:

| Ticket | Working file | SHA-256 (computed over the archived bytes) |
|---|---|---|
| PILOT-BUG-01 | decision.md | `c7cf43888718f638c1af0972fd7f358baed48a7139bd45b9aee24f144803fdb2` |
| PILOT-BUG-01 | progress.md | `001f5e5582f7bebf2dc526f6ff6d31663d361c31a221d6009ac68a7b94a3502c` |
| PILOT-BUG-01 | handoff.md | `a9c93f77b933dde8e51b81981a9fc9a47d3091a597f8d9da11a8ba740fd3c0b5` |
| PILOT-BUG-01 | state.yaml | `3d564d156796313e25b96bdfbe7237ab39fbd53648b34f6d1532dc655598e106` |
| PILOT-FEAT-01 | decision.md | `d2c77c8f1f295dc861a06734a857fb473336653cf1324d6f0cd53cda0d40266e` |
| PILOT-FEAT-01 | progress.md | `43be59451a8bc668b67bcd92d376138473865913af7ce9b10994258306413e49` |
| PILOT-FEAT-01 | handoff.md | `f8f41d084af0ae5a02ed046ca869806e39b63a658ad4feb49a79dc21d5b16443` |
| PILOT-FEAT-01 | state.yaml | `e93fa3f20f80ac45dc9acb752337e42622a09d2e2bd4fadd8dfa849e6d8e53a2` |

Corroboration: the decision.md / handoff.md values match the hashes printed
by the receiver session in `pilot/logs/codex-rereview-feat-console.txt`
(`decision.md sha256=d2c77c8f…`, `handoff.md sha256=f8f41d08…`) and the
archived `bug/handoff.md` "Artifact identity" block (`decision.md sha256
c7cf4388…`) — independent recordings made during the pilot run itself.

## Packages

| Package | SHA-256 of the ZIP file |
|---|---|
| `pilot/bug/artifacts.zip` | `0fe190b976f073df74faa56ebd8b7dcea187ef9b5e5d9adb2031f2d2065f49fb` |
| `pilot/feature/artifacts.zip` | `aad5afa4b22d9379de09c05e5a34d763e4df36e867ad7f2b6cdc2db9884158be` |

## Fresh-clone verification

(pending — appended after verifying the committed packages in a fresh
disposable kit clone)
