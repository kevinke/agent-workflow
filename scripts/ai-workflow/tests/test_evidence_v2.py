"""Tests for v2 audit binding and stale-gate rejection (SCOUT-002 Task 2).

Drives the real CLI against the V2CLITestCase fixture: a recorded gate binds the
verdict to the SHA-256 of the audited Evidence and its Audit artifact, so a
changed report or audit makes the gate stale and blocks decisionward advances.
Malformed arguments stay usage errors (exit 2), protocol rejections exit 1, and
every rejected mutation leaves the raw State bytes untouched.
"""

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import contracts  # noqa: E402
import workflow_v2  # noqa: E402
from v2_support import V2CLITestCase  # noqa: E402


class EvidenceV2Test(V2CLITestCase):
    # -- binding and staleness --------------------------------------------------

    def test_changed_report_blocks_decision_without_state_write(self):
        self.seed_v2("evidence_audit")
        self.write_evidence()
        self.write_audit()
        self.assertEqual(self.cli("set-gate", "T1", "--gate", "sufficient",
                                  "--round", "1").returncode, 0)
        before = self.state_bytes()
        path = Path(self.root) / ".ai/work/T1/evidence.md"
        path.write_text(path.read_text() + "\nAdditional observation.\n")
        self.assertEqual(self.cli("advance", "T1", "--to",
                                  "technical_decision").returncode, 1)
        self.assertEqual(self.state_bytes(), before)

    def test_changed_audit_blocks_decision_without_state_write(self):
        self.seed_v2("evidence_audit")
        self.write_evidence()
        self.write_audit()
        self.assertEqual(self.cli("set-gate", "T1", "--gate", "sufficient",
                                  "--round", "1").returncode, 0)
        before = self.state_bytes()
        path = Path(self.root) / ".ai/work/T1/evidence-audit.md"
        path.write_text(path.read_text() + "\nAdditional audit note.\n")
        self.assertEqual(self.cli("advance", "T1", "--to",
                                  "technical_decision").returncode, 1)
        self.assertEqual(self.state_bytes(), before)

    def test_validate_flags_stale_binding_after_evidence_change(self):
        self.seed_v2("evidence_audit")
        self.write_evidence()
        self.write_audit()
        self.assertEqual(self.cli("set-gate", "T1", "--gate", "sufficient",
                                  "--round", "1").returncode, 0)
        path = Path(self.root) / ".ai/work/T1/evidence.md"
        path.write_text(path.read_text() + "\nAdditional observation.\n")
        proc = self.cli("validate", "T1")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn(
            "evidence.md changed since the evidence gate was recorded "
            "(stale binding: re-audit and set-gate again)", proc.stdout)

    def test_unchanged_rerun_keeps_gate_fresh(self):
        self.seed_v2("evidence_audit")
        self.write_evidence()
        self.write_audit()
        self.assertEqual(self.cli("set-gate", "T1", "--gate", "sufficient",
                                  "--round", "1").returncode, 0)
        # Re-recording the same verdict over unchanged artifacts is idempotent.
        self.assertEqual(self.cli("set-gate", "T1", "--gate", "sufficient",
                                  "--round", "1").returncode, 0)
        self.assertEqual(self.cli("advance", "T1", "--to",
                                  "technical_decision").returncode, 0)

    def test_insufficient_followup_then_reaudit_opens_gate(self):
        self.seed_v2("evidence_audit")
        self.write_evidence(round_no=1)
        self.write_audit(gate="insufficient", round_no=1)
        self.assertEqual(self.cli("set-gate", "T1", "--gate", "insufficient",
                                  "--round", "1").returncode, 0)
        self.assertEqual(self.cli("advance", "T1", "--to",
                                  "followup_evidence").returncode, 0)
        self.assertEqual(self.cli("advance", "T1", "--to",
                                  "evidence_audit").returncode, 0)
        self.write_evidence(round_no=2)
        self.write_audit(gate="sufficient", round_no=2)
        self.assertEqual(self.cli("set-gate", "T1", "--gate", "sufficient",
                                  "--round", "2").returncode, 0)
        self.assertEqual(self.cli("advance", "T1", "--to",
                                  "technical_decision").returncode, 0)
        evidence = self.read_state()["evidence"]
        self.assertEqual(evidence["gate"], "sufficient")
        self.assertEqual(evidence["round"], 2)

    # -- rejected recordings -----------------------------------------------------

    def test_scaffold_cannot_set_gate_without_state_write(self):
        self.seed_v2("evidence_audit")
        before = self.state_bytes()
        proc = self.cli("set-gate", "T1", "--gate", "sufficient", "--round", "1")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_invalid_report_cannot_bind_gate(self):
        self.seed_v2("evidence_audit")
        path = self.write_evidence()
        self.write_audit()
        with open(path, "a", encoding="utf-8", newline="") as fh:
            fh.write("\n### DQ-01\n\n**Question:** duplicate id\n")
        before = self.state_bytes()
        proc = self.cli("set-gate", "T1", "--gate", "sufficient", "--round", "1")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_gate_metadata_mismatch_rejected(self):
        self.seed_v2("evidence_audit")
        self.write_evidence(round_no=1)
        self.write_audit(gate="sufficient", round_no=1)
        before = self.state_bytes()
        proc = self.cli("set-gate", "T1", "--gate", "insufficient", "--round", "1")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_round_metadata_mismatch_rejected(self):
        self.seed_v2("evidence_audit")
        self.write_evidence(round_no=1)
        self.write_audit(gate="sufficient", round_no=1)
        before = self.state_bytes()
        proc = self.cli("set-gate", "T1", "--gate", "sufficient", "--round", "2")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_set_gate_wrong_phase_rejected(self):
        self.seed_v2("requirement")
        before = self.state_bytes()
        proc = self.cli("set-gate", "T1", "--gate", "sufficient", "--round", "1")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    # -- usage errors and version guards ----------------------------------------

    def test_non_integer_round_is_usage_error(self):
        self.seed_v2("evidence_audit")
        self.write_evidence()
        self.write_audit()
        before = self.state_bytes()
        proc = self.cli("set-gate", "T1", "--gate", "sufficient", "--round", "abc")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_negative_round_is_usage_error(self):
        self.seed_v2("evidence_audit")
        self.write_evidence()
        self.write_audit()
        before = self.state_bytes()
        proc = self.cli("set-gate", "T1", "--gate", "sufficient", "--round", "-1")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_future_version_set_gate_rejected_without_state_write(self):
        self.seed_v2("evidence_audit")
        self.write_evidence()
        self.write_audit()
        data = self.read_state()
        data["workflow_version"] = 3
        self.write_state(data)
        before = self.state_bytes()
        proc = self.cli("set-gate", "T1", "--gate", "sufficient", "--round", "1")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_v1_fixture_semantics_unchanged(self):
        # An explicit v1 ticket: loose evidence and an unbound gate remain
        # valid, with no byte-identity binding. (Task 2 flips the default to v2,
        # so v1 is seeded explicitly rather than assumed.)
        self.seed_v1("evidence_audit")
        path = os.path.join(self.work, "evidence.md")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write("## Facts\n- FACT source artifact spec section\n")
        self.assertEqual(self.cli("set-gate", "T1", "--gate", "sufficient",
                                  "--round", "2").returncode, 0)
        state = self.read_state()
        self.assertEqual(state.get("workflow_version", 1), 1)
        self.assertEqual(state["evidence"]["gate"], "sufficient")
        self.assertNotIn("report_sha256", state["evidence"])


class EvidenceGateSyntaxTest(V2CLITestCase):
    """The public set-gate is the evidence syntax gate (HARDEN-005 Task 1).

    The six accepted-malformed inputs must be rejected with exit 1 and no
    State write; concrete supported families and a justified UNKNOWN/file
    scope must record the gate. Fixtures stay genuinely bound: every Audit
    attests the SHA-256 of the Evidence actually on disk (write_audit), never
    a fabricated successful State.
    """

    GOOD_SOURCE = "- code: src/app.py:1-2 :: main"

    # -- the six accepted-malformed inputs -------------------------------------

    def _malformed_variants(self):
        """variant name -> ("evidence" | "audit", single-argument edit)."""
        good = self.GOOD_SOURCE
        commit_line = re.compile(r"observed_commit: [0-9a-f]+", re.M)
        return {
            "missing-line": ("evidence",
                             lambda t: t.replace(good, "- code: src/app.py :: main")),
            "missing-symbol": ("evidence",
                               lambda t: t.replace(good, "- code: src/app.py:1-2")),
            "trust-me-source": ("evidence",
                                lambda t: t.replace(good, "- trust me")),
            "answered-without-fact-id": (
                "evidence",
                lambda t: t.replace("**Facts:** F-01", "**Facts:** trust me")),
            "placeholder-observed-commit": (
                "evidence",
                lambda t: commit_line.sub("observed_commit: <pending>", t,
                                          count=1)),
            "non-integer-audit-round": (
                "audit",
                lambda t: t.replace("round: 1", "round: banana", 1)),
        }

    def test_accepted_malformed_reports_rejected_by_set_gate(self):
        for name, (target, edit) in self._malformed_variants().items():
            with self.subTest(variant=name):
                self.seed_v2("evidence_audit")
                ev_path = Path(self.write_evidence())
                # The audit is written AFTER the evidence mutation, so its
                # attested hash matches the mutated Evidence on disk: a
                # rejection can only come from the syntax rule under test.
                if target == "evidence":
                    self._rewrite(ev_path, edit(ev_path.read_text("utf-8")))
                au_path = Path(self.write_audit())
                if target == "audit":
                    self._rewrite(au_path, edit(au_path.read_text("utf-8")))
                before = self.state_bytes()
                proc = self.cli("set-gate", "T1", "--gate", "sufficient",
                                "--round", "1")
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertEqual(self.state_bytes(), before)

    @staticmethod
    def _rewrite(path, text):
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)

    # -- concrete supported families pass ----------------------------------------

    FAMILIES_EVIDENCE = '''\
# Evidence - %(ticket)s

## Metadata

```yaml
artifact_type: evidence
format_version: 1
ticket_id: %(ticket)s
round: %(round)d
observed_commit: %(commit)s
dirty_changes: []
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

**Facts:** F-01, F-02, F-03, F-04

### DQ-02

**Question:** Does any caller outside the fixture invoke the entry point?

**Decision affected:** regression surface

**Evidence targets:** consuming repositories

**Answer:** UNKNOWN

**Facts:** UNKNOWN

## Findings

### F-01 [FACT]

**Statement:** The entry point is main() in src/app.py.

**Questions:** DQ-01

**Sources:**
- code: src/app.py:1-2 :: main
- code: my dir/app.py:1-2 :: file scope (reason: spaced path with no named symbol)
- config: conf/settings.ini:3-4 :: cache.ttl
- data: data/roster.csv:8-10 :: row[id=42]

**Method:** static

**Scope:** the committed fixture only

### F-02 [FACT]

**Statement:** Running the fixture prints 42 and exits 0.

**Questions:** DQ-01

**Sources:**
- runtime: python src/app.py / input: none / observed result: stdout 42 / exit status: 0
- runtime: python src/app.py --json / input: --json flag / result: stdout {"value": 42} / exit: 0

**Method:** execution

**Scope:** single run on the observed commit

### F-03 [FACT]

**Statement:** No other module calls main(); the fixture has a single consumer.

**Questions:** DQ-01

**Sources:**
- negative search: scope src/*.py for callers of main / exclusions: none / result: no matches
- negative search: scope docs/notes/*.md for stale entry-point notes / exclusions: none / result: no matches

**Method:** static

**Scope:** the fixture directory; searches never require a fabricated file

### F-04 [INFERENCE]

**Statement:** The entry point is stable because the module defines exactly one top-level function.

**Questions:** DQ-01

**Sources:**
- inference basis: F-01

**Basis:** F-01 shows the module layout the inference rests on.

**Method:** inference

**Scope:** inference from F-01 only

### F-05 [UNKNOWN]

**Statement:** External callers of main() are unobserved.

**Questions:** DQ-02

**Sources:**
- UNKNOWN: external callers of main() / collect at: consuming repository search for app.main calls

**Method:** unknown

**Scope:** open; see Unknowns

## Unknowns

- **U-01 / DQ-02:** external callers unobserved; next collection step: search consuming repositories.

## Handoff

- **Established Fact IDs:** F-01, F-02, F-03, F-04
- **Decisions still required:** none
- **Missing evidence:** external callers (U-01)
- **Already investigated:** src/app.py
- **Stopping reason:** fixture report complete
'''

    def test_concrete_families_and_justified_unknown_pass_set_gate(self):
        self.seed_v2("evidence_audit")
        head = self._git("rev-parse", "HEAD").stdout.strip()
        text = self.FAMILIES_EVIDENCE % {
            "ticket": self.TICKET, "round": 1, "commit": head}
        path = os.path.join(self.work, "evidence.md")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        self.write_audit()
        report = contracts.read_artifact(path, "evidence")
        self.assertEqual(contracts.validate_evidence(report, self.TICKET), [])
        proc = self.cli("set-gate", "T1", "--gate", "sufficient", "--round", "1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        state = self.read_state()
        self.assertEqual(state["evidence"]["gate"], "sufficient")


class TransitionTest(unittest.TestCase):
    """The shared v2 transition/route helpers exposed in workflow_v2."""

    def test_next_action_known_phase(self):
        route = workflow_v2.next_action({}, "evidence_collection")
        self.assertEqual(set(route), {"role", "action", "task"})
        self.assertEqual(route["role"], "scout")
        self.assertIsNone(route["task"])

    def test_next_action_done_is_cleared(self):
        self.assertEqual(workflow_v2.next_action({}, "done"),
                         {"role": None, "action": None, "task": None})

    def test_check_transition_accepts_v1_edge(self):
        workflow_v2.check_transition(".", {"phase": "requirement"},
                                     "evidence_collection")

    def test_check_transition_rejects_illegal_target(self):
        with self.assertRaises(contracts.ContractError):
            workflow_v2.check_transition(".", {"phase": "requirement"},
                                         "technical_decision")

    def test_check_transition_rejects_unknown_phase(self):
        with self.assertRaises(contracts.ContractError):
            workflow_v2.check_transition(".", {"phase": "bogus"},
                                         "requirement")


if __name__ == "__main__":
    unittest.main()
