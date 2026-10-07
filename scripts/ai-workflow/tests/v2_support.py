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
    "review": ("checkpoint-handoff", "review and hand off"),
    "done": (None, None),
}

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


class V2CLITestCase(unittest.TestCase):
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
                              capture_output=True, text=True,
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
