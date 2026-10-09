# 12: LF-stable installer protection template

Ticket ID: HARDEN-012
Type: task
Status: published — delivery commit 86a823c verified on a fresh checkout 2026-10-09
Blocked by: None
Parent: [C11 LF-stable template](../spec.md#c11--lf-stable-installer-protection-template-harden-012)
Source findings: O5; [disposition](../review-disposition.md)
Plan: [delivery closure plan](../../../docs/superpowers/plans/2026-10-09-harden-12.md);
bounded fix already applied, this Ticket records delivery and verification.

## What changed

Root `.gitattributes` pins only
`/.ai/workflow/templates/work.gitattributes text eol=lf`. The worktree template
was restored to `** -text\n`, matching HEAD. Installer behavior and existing
custom target attributes remain unchanged. Root attributes are published in
delivery commit `86a823c`; no other path entered that commit.

## Scope and ownership

Only root `.gitattributes` and the existing protection template belong to this
fix. Do not normalize other files, bound pilot artifacts or registered Plans;
do not change global Git configuration, raw-byte digests or installer semantics.

## Acceptance criteria

- [x] Worktree template is LF and matches the existing HEAD blob exactly.
- [x] Effective attributes for the template are `text=set`, `eol=lf`.
- [x] LF/CRLF source forms, committed and freshly cloned with local autocrlf
      true/false/input, yield LF template and actual init output in all six cases.
- [x] Existing install/transport tests pass (17 tests), including custom-file
      preservation, repeated-init stability and mixed-byte artifact transport.
- [x] Complete integration passes: 400 tests, OK, exit 0.
- [x] Before/after source hashing confirms no other pre-existing tracked file
      was changed by the fix; original pilot work bytes and ZIPs were preserved.
- [x] Publish the root attribute rule in a repository commit when authorized;
      verify fresh checkout of that committed revision before marking published.

## Verification record

The pre-fix full suite had four failure assertions in three tests, all
`b"** -text\r\n" != b"** -text\n"`; the new-work test ran both autocrlf cases.

After the two-file fix, in an isolated copy of HEAD 1145c24 with current working
bytes and the root attribute rule:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest test_init test_transport -v
# from scripts/ai-workflow/tests: Ran 17 tests; OK

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts/ai-workflow/tests -p 'test_*.py'
# from kit root: Ran 400 tests in 163.087s; OK; exit 0
```

A separate real-Git matrix used disposable commits/clones and the real init
module: both LF and CRLF source inputs times autocrlf true, false and input.
All six cloned templates and installed attribute outputs equalled `** -text\n`.
This is local verification, not evidence that the uncommitted rule is published.

### Publication evidence (2026-10-09)

Delivery commit `86a823c053182aa2d2dad7d7e919f1c08a3a9992`
(`fix: keep installer protection template LF across checkouts`) stages only
root `.gitattributes`; `git diff --cached --name-only` listed that single path
and the committed blob is LF-terminated. The template needed no change: its
working bytes and `git show HEAD:` blob were already `b"** -text\n"`, and
`git check-attr text eol` reports `text: set`, `eol: lf`.

Six-case matrix re-run against that committed revision, each case an
independent disposable `--no-local` clone checked out on a named branch, with
`core.autocrlf` set locally in the seed repository and per-command (`-c`) for
the fresh clone — never in global configuration:

| Template seed | autocrlf | Staged blob | Cloned template | `init.init` output | Custom target attrs |
|---|---|---|---|---|---|
| LF | true | `b"** -text\n"` | `b"** -text\n"` | `b"** -text\n"` | preserved |
| LF | false | `b"** -text\n"` | `b"** -text\n"` | `b"** -text\n"` | preserved |
| LF | input | `b"** -text\n"` | `b"** -text\n"` | `b"** -text\n"` | preserved |
| CRLF | true | `b"** -text\n"` | `b"** -text\n"` | `b"** -text\n"` | preserved |
| CRLF | false | `b"** -text\n"` | `b"** -text\n"` | `b"** -text\n"` | preserved |
| CRLF | input | `b"** -text\n"` | `b"** -text\n"` | `b"** -text\n"` | preserved |

6/6 passed. Both seed forms staged to the identical LF blob, so the seed commit
is legitimately a no-op in every case; that normalization is itself the
asserted property, and the discriminating weight is carried by the fresh
clone/checkout and install steps.

Negative control confirming the matrix can fail: at the pre-fix revision
`3a4a980` (no root `.gitattributes`), a `--no-local` clone with
`core.autocrlf=true` checks the template out as `b"** -text\r\n"`, while
autocrlf `false` and `input` yield `b"** -text\n"`. The same clone at
`86a823c` with `autocrlf=true` yields `b"** -text\n"`. This host's local
`core.autocrlf` is `true`, which is why the unfixed revision fails here.

Focused suite on a fresh `--no-local` clone of `86a823c`, from its
`scripts/ai-workflow/tests`:

```text
PYTHONDONTWRITEBYTECODE=1 python -m unittest test_init test_transport -v
# Ran 17 tests in 2.893s; OK; exit 0
```

The previously recorded 400-test full-suite result stays local evidence for the
pre-publication snapshot; full discovery is rerun under HARDEN-010 integration.

## Comments

- 2026-10-09 — Created retroactively to record the authorized local CRLF fix.
  No duplicate implementation task or new global normalization is required.
- 2026-10-09 — Added a single-task delivery plan; retain existing local evidence.
  Commit and fresh published-revision checks remain pending.
- 2026-10-09 — Published as `86a823c` staging only root `.gitattributes`; the
  template already matched HEAD so it entered no diff. Six-case matrix rerun
  against the committed revision passed 6/6 with a pre-fix negative control at
  `3a4a980` showing `b"** -text\r\n"` under `autocrlf=true`. Fresh-checkout
  `test_init test_transport` ran 17 tests, OK, exit 0. Publication acceptance is
  now closed; no other tracked file was touched and earlier local evidence,
  source hashes and pilot raw bytes are unchanged.
