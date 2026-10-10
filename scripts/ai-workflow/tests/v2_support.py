"""Shared test fixture for workflow-version-2 contract tests (SCOUT-002).

V2CLITestCase builds a throwaway Git repository, installs the protocol through
the real `init` CLI, starts one ticket through the real `start` CLI, and then
seeds an explicit workflow_version=2 State. Git identity comes from the
environment only — the global configuration is never touched.

Evidence/Audit helpers always write valid concrete reports bound to the actual
code fixture and its HEAD; a gate's own hash is never filled in to test that
gate (per the common plan's fixture rules).
"""

import hashlib
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import state  # noqa: E402

KIT_CLI = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")

CODE_FIXTURE = os.path.join("src", "app.py")
CODE_TEXT = "def main():\n    return 42\n"

# An unupgraded v1 `templates/state.yaml` (the pre-flip shipped default). Tests
# that assert v1 semantics plant this into a target so `start`/`adopt` resolve
# it (Ruling C) instead of the kit's v2 bundled template. Task 2 flips that
# default, so v1 is never assumed implicitly.
V1_TEMPLATE = """\
schema_version: 1
workflow_version: 1
ticket:
  id: <ticket-id>
  title: <ticket title>
phase: requirement
status: active
repository:
  base_commit: <base commit hash>
  branch: <branch name>
source_artifacts:
  spec:
    path: null
  ticket:
    path: null
  plan:
    path: null
artifacts:
  evidence: evidence.md
  evidence_audit: evidence-audit.md
  decision: decision.md
  progress: progress.md
  handoff: handoff.md
evidence:
  round: 0
  gate: insufficient
implementation:
  current_task: 0
  total_tasks: 0
  completed_tasks: []
escalation:
  required: false
  scope: machine
  reason: null
claim:
  harness: null
  model: null
  claimed_at: null
next_action:
  role: checkpoint-handoff
  action: advance phase from requirement to evidence_collection
  task: null
provenance:
  last_harness: null
  last_model: null
updated_at: <ISO-8601 timestamp>
"""


def install_v1_templates(root):
    """Plant an unupgraded v1 state.yaml template into `root`.

    After Task 2 the kit's bundled default is v2, so a target without this
    explicit v1 template would scaffold v2 work. Writing only `state.yaml` into
    the installed template dir keeps the v1 version semantics while report
    scaffolds (if `init` already installed them) stay untouched. Returns the
    path written.
    """
    tmpl_dir = os.path.join(root, ".ai", "workflow", "templates")
    os.makedirs(tmpl_dir, exist_ok=True)
    dest = os.path.join(tmpl_dir, "state.yaml")
    with open(dest, "w", encoding="utf-8", newline="") as fh:
        fh.write(V1_TEMPLATE)
    return dest


# Phase-appropriate next_action routes for seeded v2 tickets.
ROUTES = {
    "requirement": ("workflow-bootstrap",
                    "advance phase from requirement to evidence_collection"),
    "evidence_collection": ("scout", "collect evidence into evidence.md"),
    "evidence_audit": ("evidence-auditor", "audit evidence sufficiency"),
    "followup_evidence": ("scout", "collect the missing evidence"),
    "technical_decision": ("technical-decision", "write decision.md"),
    "planning": ("executor-plan", "write the implementation plan"),
    "implementation": ("ticket-executor", "implement current task"),
    "review": ("reviewer", "review and hand off"),
    "done": (None, None),
}

# v1 Tickets keep the frozen route table: in `review` the route is the
# mechanical checkpoint-handoff, not the v2 independent `reviewer`.
V1_ROUTES = dict(ROUTES)
V1_ROUTES["review"] = ("checkpoint-handoff", "review and hand off")

DECISION_TEMPLATE = '''\
# Decision - %(ticket)s

## Chosen approach

Implement the bounded fixture change described by F-01.

## Invariants

main() keeps returning 42.
'''

EVIDENCE_TEMPLATE = '''\
# Evidence - %(ticket)s

## Metadata

```yaml
artifact_type: evidence
format_version: 1
ticket_id: %(ticket)s
round: %(round)d
observed_commit: %(commit)s
dirty_changes: %(dirty)s
created_at: 2026-10-07T00:00:00+00:00
scout_harness: v2-fixture
scout_model: v2-fixture
```

## Decision Questions

### DQ-01

**Question:** Which function is the entry point of the fixture?

**Decision affected:** implementation scope

**Evidence targets:** src/app.py

**Answer:** ANSWERED

**Facts:** F-01

## Findings

### F-01 [FACT]

**Statement:** The entry point is main() in src/app.py.

**Questions:** DQ-01

**Sources:**
- code: src/app.py:1-2 :: main

**Method:** static

**Scope:** the committed fixture only

## Unknowns

None.

## Handoff

- **Established Fact IDs:** F-01
- **Decisions still required:** none
- **Missing evidence:** none
- **Already investigated:** src/app.py
- **Stopping reason:** fixture report complete
'''

AUDIT_HEADINGS = [
    "Is the evidence sufficient to enter technical_decision?",
    "What is missing?",
    "Why might the gap change a decision?",
    "What should the next scout collect precisely?",
]

_AUDIT_ANSWERS = {
    "sufficient": [
        "Yes. DQ-01 is answered and F-01 carries a code anchor into the fixture.",
        "Nothing material; the single decision question is fully covered.",
        "Not applicable - no gap remains that could change the decision.",
        "Not applicable - no further collection is required.",
    ],
    "insufficient": [
        "No. The report does not yet close the decision question.",
        "A runtime confirmation of F-01 and its exit status is missing.",
        "Without runtime confirmation the entry-point claim could change the "
        "implementation scope.",
        "Run the fixture and record the observed result and exit status.",
    ],
}

AUDIT_TEMPLATE = '''\
# Evidence Audit - %(ticket)s

## Metadata

```yaml
artifact_type: evidence-audit
format_version: 1
ticket_id: %(ticket)s
round: %(round)d
gate: %(gate)s
evidence_sha256: %(sha)s
```

## %(h0)s

%(a0)s

## %(h1)s

%(a1)s

## %(h2)s

%(a2)s

## %(h3)s

%(a3)s
'''


def valid_evidence(ticket_id, round_no, observed_commit, dirty="[]"):
    """A complete, structurally valid Evidence report bound to `observed_commit`."""
    return EVIDENCE_TEMPLATE % {
        "ticket": ticket_id, "round": round_no,
        "commit": observed_commit, "dirty": dirty,
    }


def valid_audit(ticket_id, gate, round_no, evidence_sha256):
    """A complete, structurally valid Audit of the Evidence with that hash."""
    answers = _AUDIT_ANSWERS[gate]
    return AUDIT_TEMPLATE % {
        "ticket": ticket_id, "gate": gate, "round": round_no,
        "sha": evidence_sha256,
        "h0": AUDIT_HEADINGS[0], "a0": answers[0],
        "h1": AUDIT_HEADINGS[1], "a1": answers[1],
        "h2": AUDIT_HEADINGS[2], "a2": answers[2],
        "h3": AUDIT_HEADINGS[3], "a3": answers[3],
    }


PLAN_HEADER = '''\
# Plan - %(ticket)s

## Metadata

```yaml
artifact_type: plan
format_version: 1
ticket_id: %(ticket)s
task_count: %(count)d
```

'''

PLAN_TASK = '''\
## Task %(n)d

### Objective
Carry out bounded step %(n)d for the fixture.

### Inputs
F-01 decision recorded in decision.md.

### Allowed changes
src/app.py only.

### Protected scope
The public read() behavior of the fixture.

### Invariants
main() keeps returning 42.

### Acceptance criteria
Step %(n)d is observably complete and no protected behavior changed.

### Verification
Run `python -c "import app"` and expect exit status 0.

### Dependencies
%(deps)s

### Escalation conditions
Stop and escalate if the decision no longer covers this step.

'''


def valid_plan(ticket_id, total):
    """A structurally valid Plan with `total` ordered, bounded tasks."""
    parts = [PLAN_HEADER % {"ticket": ticket_id, "count": total}]
    for n in range(1, total + 1):
        deps = "N/A (first task)" if n == 1 else "Task 1"
        parts.append(PLAN_TASK % {"n": n, "deps": deps})
    return "".join(parts)


REVIEW_TEMPLATE = '''\
# Review - %(ticket)s

## Metadata

```yaml
artifact_type: review
format_version: 1
ticket_id: %(ticket)s
reviewed_commit: "%(commit)s"
plan_sha256: "%(plan_sha)s"
verdict: %(verdict)s
```

## Acceptance results

%(acceptance)s

## Verification results

%(verification)s

## Findings

%(findings)s

## Required rework

%(rework)s
'''


def valid_review(ticket_id, verdict, reviewed_commit, plan_sha256):
    """A concrete, structurally valid Review bound to a commit and Plan hash.

    A `pass` uses the explicit `None` for Findings/Required rework; a
    `changes_requested` records substantive findings and rework. The hex
    identities are quoted so the restricted parser keeps them strings even
    when a fixture commit's abbreviation happens to be all decimal digits.
    """
    passing = verdict == "pass"
    return REVIEW_TEMPLATE % {
        "ticket": ticket_id, "verdict": verdict,
        "commit": reviewed_commit, "plan_sha": plan_sha256,
        "acceptance": "Task 1 acceptance criteria met: the reviewed change "
                      "keeps main() returning 42.",
        "verification": "Ran `python -c \"import app\"`; observed exit status 0.",
        "findings": "None" if passing
                    else "F-01: the reviewed change needs a boundary assertion.",
        "rework": "None" if passing
                  else "Append a task that adds the boundary assertion.",
    }


# ---------------------------------------------------------------------------
# Handoff fixtures (HARDEN-007): the untouched template scaffold and a
# concrete, readiness-valid alternative.
# ---------------------------------------------------------------------------

_KIT_WORKFLOW_DIR = os.path.join(
    os.path.dirname(os.path.dirname(  # repo root: tests/ -> ... -> repo
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    ".ai", "workflow")

HANDOFF_CONCRETE_TEMPLATE = '''\
# Handoff - %(ticket)s

## What was done

Implemented the registered fixture change: src/feature.py defines
`feature()` and every task of the %(total)d-task registered Plan is
complete (main() still returns 42). Code literals like `Pair<T>` and
comparisons like `a < b` are ordinary content, never placeholders.

## What remains

%(remains)s

## Important discoveries

- The fixture entry point is main() in src/app.py (F-01, evidence round %(round)d).

## Artifact identity

%(artifacts)s

## Verification limits

Verified by static reading of src/feature.py and by running
`python -c "import app"` (observed exit status 0). Runtime behavior beyond
the import was NOT verified; static reading is not runtime evidence.

## Known relevant drift

- Repository HEAD: %(head)s
- Evidence observed commit: %(evidence_commit)s — assessed against HEAD
- Review reviewed commit / verdict: %(review)s
- Changed paths that matter: %(changed)s

## Current failure (if any)

%(failure)s

## Do not repeat

Do not hand-edit implementation counters; reconcile with register-plan.

## Next recommended action

%(next)s

## Repository State

- Branch: %(branch)s
- HEAD: %(head)s
- Uncommitted files: %(dirty)s
- Test status: %(test_status)s
'''


def scaffold_handoff(ticket_id="T1"):
    """The untouched Handoff template as `start` scaffolds it.

    Reads the kit's authoritative template and applies the same single
    `<ticket-id>` replacement `start._scaffold_template` performs, so the
    baseline is exactly what an early draft looks like on disk.
    """
    path = os.path.join(_KIT_WORKFLOW_DIR, "templates", "handoff.md")
    with open(path, encoding="utf-8") as fh:
        return fh.read().replace("<ticket-id>", ticket_id)


def valid_handoff(ticket_id, branch, head, **overrides):
    """A concrete, readiness-valid Handoff for the fixture repository.

    Every field is concrete fixture data; keyword overrides replace
    individual fields (e.g. `failure="None"`,
    `changed="N/A - no relevant paths changed"`), so the legitimate
    explicit-None / justified-N-A / code-literal cases stay expressible
    without weakening the defaults.
    """
    fields = {
        "ticket": ticket_id, "branch": branch, "head": head,
        "total": 1, "round": 1,
        "remains": "Record the review verdict with set-review, then "
                   "advance --to done.",
        "artifacts": "- Evidence: evidence.md (round 1)\n"
                     "- Evidence audit: evidence-audit.md (gate sufficient)\n"
                     "- Decision: decision.md\n"
                     "- Plan: plan.md (registered)\n"
                     "- Review: none (no verdict recorded yet)",
        "evidence_commit": head,
        "review": "none / none (no verdict recorded yet)",
        "changed": "none",
        "failure": "none",
        "test_status": "passing",
        "dirty": "none",
        "next": "Reviewer: record the verdict with set-review, then advance "
                "--to done; blockers to resolve first: none.",
    }
    fields.update(overrides)
    return HANDOFF_CONCRETE_TEMPLATE % fields


class IndexHintFixture:
    """Git index-hint primitives shared by every v2 suite that pins drift.

    `assume-unchanged` and `skip-worktree` are hints that make `git diff` skip an
    entry entirely, so an equal-size edit or a deletion on a hinted path can hide
    from the read-only drift assessment. These helpers set and clear them for any
    regression pin, so no suite carries its own copy of index-mutating fixture
    code.

    Git pathspecs take forward slashes while file I/O needs the platform
    separator, so targets are named repo-relative with `/`. Each bit needs its
    own command — one `update-index` cannot express the combination — which is
    also why the assessment under test clears them separately.
    """

    INDEX_HINTS = ("assume-unchanged", "skip-worktree", "both")

    def _set_flag(self, path, flag):
        """Set one or both index hints via separate Git commands."""
        if flag in ("assume-unchanged", "both"):
            proc = self._git("update-index", "--assume-unchanged", path)
            self.assertEqual(proc.returncode, 0, proc.stderr)
        if flag in ("skip-worktree", "both"):
            proc = self._git("update-index", "--skip-worktree", path)
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def _clear_flag(self, path, flag):
        """Clear one or both index hints via separate Git commands."""
        if flag in ("assume-unchanged", "both"):
            proc = self._git("update-index", "--no-assume-unchanged", path)
            self.assertEqual(proc.returncode, 0, proc.stderr)
        if flag in ("skip-worktree", "both"):
            proc = self._git("update-index", "--no-skip-worktree", path)
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def _flagged_edit(self, flag, rel="src/feature.py",
                      old="return 1", new="return 9"):
        """Hint `rel`, then rewrite it at an unchanged byte size.

        The equal-length rewrite keeps detection from relying on a size change,
        so only a content comparison can report the edit.
        """
        self._set_flag(rel, flag)
        full = os.path.join(self.root, rel)
        with open(full, "r", encoding="utf-8", newline="") as fh:
            original = fh.read()
        dirty = original.replace(old, new)
        self.assertEqual(len(dirty), len(original))
        self.assertNotEqual(dirty, original)
        with open(full, "w", encoding="utf-8", newline="") as fh:
            fh.write(dirty)

    def _flagged_delete(self, flag, rel="src/feature.py"):
        """Hint `rel`, then delete it from the worktree."""
        self._set_flag(rel, flag)
        os.remove(os.path.join(self.root, rel))

    def _unhint_and_rewind(self, rel):
        """Clear both hints and rewind `rel`'s worktree bytes from the index.

        Used from a `finally` in each `subTest` body: a failing assertion aborts
        the rest of that body, so cleanup that only runs on the success path
        would leak a hint and a dirty or deleted path into the next subcase —
        where the leaked dirt alone would satisfy every later "this is stale"
        assertion, letting a partial regression pass. `git checkout` skips a
        `skip-worktree` path, so hints are cleared first.
        """
        self._clear_flag(rel, "both")
        proc = self._git("checkout", "--", rel)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def _snapshot(self, rel):
        """Bytes, timestamps and hint flags a read-only probe must not move.

        Captured *before* each probe rather than after: a baseline taken once a
        probe has already run would compare that probe's own write against
        itself, so the snapshot has to precede the first command being judged.

        The `.git` directory's file set is part of it deliberately. An
        allow-list of index bytes, timestamps and flags is blind to a check that
        *creates* a new file in the repository — an orphan `sharedindex.<oid>`
        written into the common dir by honoring `core.splitIndex`, say — so the
        file set is compared, not only the files the test foresaw.
        """
        index_path = os.path.join(self.root, ".git", "index")
        review_path = os.path.join(self.work, "review.md")
        with open(index_path, "rb") as fh:
            index_bytes = fh.read()
        with open(review_path, "rb") as fh:
            review_bytes = fh.read()
        return {
            "state": self.state_bytes(),
            "index": index_bytes,
            "index_mtime": os.stat(index_path).st_mtime_ns,
            "flags": self._git("ls-files", "-v", "-z", "--", rel).stdout,
            "review": review_bytes,
            "review_mtime": os.stat(review_path).st_mtime_ns,
            "gitdir": sorted(os.listdir(os.path.join(self.root, ".git"))),
        }

    def _stale_lines(self, text):
        """The lines reporting a stale binding, for path-attribution checks.

        `resume` also prints an Evidence anchor notice listing every path changed
        since the recorded observed commit, which names the very file these hint
        pins mutate even while the Review binding is perfectly current.
        Asserting the path appears somewhere in the output would therefore pass
        with no drift blocker at all, so the pins match it against the staleness
        lines specifically instead.
        """
        return [line for line in text.splitlines() if "stale" in line]

    def _assert_unchanged(self, rel, snap):
        """Assert nothing a read-only probe could touch actually moved."""
        index_path = os.path.join(self.root, ".git", "index")
        review_path = os.path.join(self.work, "review.md")
        with open(index_path, "rb") as fh:
            self.assertEqual(fh.read(), snap["index"],
                             ".git/index bytes changed")
        self.assertEqual(os.stat(index_path).st_mtime_ns, snap["index_mtime"],
                         ".git/index mtime changed")
        self.assertEqual(
            self._git("ls-files", "-v", "-z", "--", rel).stdout, snap["flags"],
            "index hints changed: the probe cleared the real index")
        self.assertEqual(self.state_bytes(), snap["state"])
        with open(review_path, "rb") as fh:
            self.assertEqual(fh.read(), snap["review"],
                             "review.md bytes changed")
        self.assertEqual(os.stat(review_path).st_mtime_ns,
                         snap["review_mtime"])
        self.assertEqual(sorted(os.listdir(os.path.join(self.root, ".git"))),
                         snap["gitdir"],
                         "the probe created or removed a file under .git")


class V2CLITestCase(IndexHintFixture, unittest.TestCase):
    """Temporary-repo fixture driving the real CLI (cwd is the target repo)."""

    TICKET = "T1"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.work = os.path.join(self.root, ".ai", "work", self.TICKET)

        init = self._git("init", "-q")
        self.assertEqual(init.returncode, 0, init.stderr)
        self.commit_code(CODE_FIXTURE, CODE_TEXT)

        proc = self.cli("init")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = self.cli("start", self.TICKET, "--title", "v2 fixture ticket")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def tearDown(self):
        self._tmp.cleanup()

    # -- environment -----------------------------------------------------------

    def _env(self):
        env = dict(os.environ)
        env.update({
            "GIT_AUTHOR_NAME": "v2-fixture",
            "GIT_AUTHOR_EMAIL": "v2-fixture@local",
            "GIT_COMMITTER_NAME": "v2-fixture",
            "GIT_COMMITTER_EMAIL": "v2-fixture@local",
        })
        return env

    def _git(self, *args):
        return subprocess.run(["git", "-C", self.root] + list(args),
                              capture_output=True, text=True, env=self._env())

    def cli(self, *args):
        """Run the real CLI with cwd=temp repo; return CompletedProcess."""
        return subprocess.run([sys.executable, KIT_CLI] + list(args),
                              capture_output=True, text=True, encoding="utf-8",
                              cwd=self.root, env=self._env())

    # -- state access ------------------------------------------------------------

    def _state_path(self):
        return os.path.join(self.work, "state.yaml")

    def read_state(self):
        return state.load_file(self._state_path())

    def state_bytes(self):
        with open(self._state_path(), "rb") as fh:
            return fh.read()

    def write_state(self, data):
        state.save_file(self._state_path(), data)

    def seed_v2(self, phase):
        """Explicit pending v2 state at `phase` with a phase-appropriate route."""
        role, action = ROUTES[phase]
        data = self.read_state()
        data["workflow_version"] = 2
        data["phase"] = phase
        data["status"] = "active"
        data["evidence"] = {"round": 0, "gate": "insufficient"}
        data["next_action"] = {"role": role, "action": action, "task": None}
        self.write_state(data)

    def seed_v1(self, phase):
        """Explicit workflow_version=1 state at `phase`, phase-appropriate route.

        Never assumes the bundled template is v1 (Task 2 flips it): the version
        is written explicitly. The `review` route is the frozen v1
        checkpoint-handoff, not the v2 reviewer.
        """
        role, action = V1_ROUTES[phase]
        data = self.read_state()
        data["workflow_version"] = 1
        data["phase"] = phase
        data["status"] = "active"
        data["evidence"] = {"round": 0, "gate": "insufficient"}
        data["next_action"] = {"role": role, "action": action, "task": None}
        self.write_state(data)

    def prepare_v2_review(self, total=1):
        """Bring a v2 ticket to `review` with a coherent completed Plan + audit.

        Drives the public commands: a current sufficient gate, a registered
        `total`-task Plan with every task complete, and `decision.md` written and
        committed. The tree is committed so the returned commit is a clean,
        reviewed HEAD ready for `write_review` + `set-review`.
        """
        self.seed_v2("evidence_audit")
        self.write_evidence(round_no=1)
        self.write_audit(gate="sufficient", round_no=1)
        proc = self.cli("set-gate", self.TICKET, "--gate", "sufficient",
                        "--round", "1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for target in ("technical_decision", "planning"):
            proc = self.cli("advance", self.TICKET, "--to", target)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        rel = self.write_plan(total)
        proc = self.cli("register-plan", self.TICKET, "--path", rel,
                        "--total", str(total))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = self.cli("advance", self.TICKET, "--to", "implementation")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.write_decision()
        self.commit_code("src/feature.py", "def feature():\n    return 1\n")
        for _ in range(total):
            proc = self.cli("complete-task", self.TICKET, "--total", str(total))
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.write_handoff()
        proc = self.cli("advance", self.TICKET, "--to", "review")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.commit_all("fixture: prepare review tree")
        return self._git("rev-parse", "HEAD").stdout.strip()

    # -- artifacts -----------------------------------------------------------------

    def _write_artifact(self, name, text):
        path = os.path.join(self.work, name)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return path

    def write_evidence(self, round_no=1):
        head = self._git("rev-parse", "HEAD").stdout.strip()
        return self._write_artifact(
            "evidence.md", valid_evidence(self.TICKET, round_no, head))

    def write_audit(self, gate="sufficient", round_no=1):
        evidence_path = os.path.join(self.work, "evidence.md")
        with open(evidence_path, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
        return self._write_artifact(
            "evidence-audit.md", valid_audit(self.TICKET, gate, round_no, digest))

    def write_plan(self, total=1, name="plan.md"):
        """Write a valid `total`-task Plan; return its repo-relative path."""
        full = os.path.join(self.work, name)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="") as fh:
            fh.write(valid_plan(self.TICKET, total))
        return os.path.relpath(full, self.root)

    def write_decision(self, name="decision.md"):
        """Write a concrete decision.md; return its repository-relative path.

        `implementation -> review` requires decision.md on a v2 Ticket, so the
        review lifecycle fixtures write it before the reviewed commit.
        """
        return self._write_artifact(name, DECISION_TEMPLATE % {"ticket": self.TICKET})

    def write_review(self, verdict, reviewed_commit=None, name="review.md"):
        """Write a concrete Review bound to the registered Plan and a commit.

        `reviewed_commit` defaults to the repository HEAD; the Plan path/SHA are
        read from State (`source_artifacts.plan`) so the artifact is genuinely
        bound. Returns the artifact path.
        """
        if reviewed_commit is None:
            reviewed_commit = self._git("rev-parse", "HEAD").stdout.strip()
        data = self.read_state()
        plan_ref = (data.get("source_artifacts") or {}).get("plan") or {}
        text = valid_review(self.TICKET, verdict, reviewed_commit,
                            plan_ref.get("sha256"))
        return self._write_artifact(name, text)

    def write_handoff(self, ticket_id=None, **overrides):
        """Write a concrete handoff.md into the ticket work dir; return its text.

        Branch, HEAD and uncommitted files are read from the real fixture
        repository, and the Artifact identity bullets cite the actual recorded
        bindings (each computed from the artifact's real bytes; an item that
        does not exist is the explicit `none`, never a fake gate hash). Field
        overrides pass through to `valid_handoff`.
        """
        tid = ticket_id or self.TICKET
        work = os.path.join(self.root, ".ai", "work", tid)
        head = self._git("rev-parse", "HEAD").stdout.strip()
        branch = self._git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        status = self._git("status", "--porcelain")
        dirty = [line[3:].strip().replace("\\", "/")
                 for line in status.stdout.splitlines() if line.strip()]
        data = state.load_file(os.path.join(work, "state.yaml"))

        def digest(name):
            with open(os.path.join(work, name), "rb") as fh:
                return hashlib.sha256(fh.read()).hexdigest()

        bullets = []
        for label, name in (("Evidence", "evidence.md"),
                            ("Evidence audit", "evidence-audit.md"),
                            ("Decision", "decision.md"),
                            ("Review", "review.md")):
            if os.path.exists(os.path.join(work, name)):
                bullets.append("- %s: %s sha256 %s" % (label, name, digest(name)))
            else:
                bullets.append("- %s: none (not recorded yet)" % label)
        plan_ref = (data.get("source_artifacts") or {}).get("plan") or {}
        plan_path = plan_ref.get("path")
        if plan_path and os.path.exists(os.path.join(self.root, plan_path)):
            with open(os.path.join(self.root, plan_path), "rb") as fh:
                plan_sha = hashlib.sha256(fh.read()).hexdigest()
            bullets.append("- Plan: %s sha256 %s (registered)"
                           % (plan_path, plan_sha))
        elif plan_path:
            bullets.append("- Plan: %s (registered; missing on disk)" % plan_path)
        else:
            bullets.append("- Plan: none (not registered yet)")

        evidence = data.get("evidence") or {}
        text = valid_handoff(
            tid, branch, head,
            total=(data.get("implementation") or {}).get("total_tasks") or 1,
            round=evidence.get("round") or 1,
            artifacts="\n".join(bullets),
            dirty=", ".join(dirty) if dirty else "none",
            **overrides)
        self._write_artifact_into(work, "handoff.md", text)
        return text

    def _write_artifact_into(self, work_dir, name, text):
        path = os.path.join(work_dir, name)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return path

    # -- repository ------------------------------------------------------------------

    def capture_files(self):
        """Snapshot of every file under the repo, excluding Git internals."""
        files = {}
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d != ".git"]
            for name in filenames:
                full = os.path.join(dirpath, name)
                with open(full, "rb") as fh:
                    files[os.path.relpath(full, self.root)] = fh.read()
        return files

    def commit_code(self, path, text):
        """Commit `text` at repo-relative `path`; return the new HEAD."""
        full = os.path.join(self.root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        self.assertEqual(self._git("add", "-A").returncode, 0)
        commit = self._git("commit", "-q", "-m", "fixture: %s" % path)
        self.assertEqual(commit.returncode, 0, commit.stderr)
        return self._git("rev-parse", "HEAD").stdout.strip()

    def commit_all(self, message="fixture: commit tree"):
        """Stage and commit every change; return the new HEAD."""
        self.assertEqual(self._git("add", "-A").returncode, 0)
        commit = self._git("commit", "-q", "-m", message)
        self.assertEqual(commit.returncode, 0, commit.stderr)
        return self._git("rev-parse", "HEAD").stdout.strip()
