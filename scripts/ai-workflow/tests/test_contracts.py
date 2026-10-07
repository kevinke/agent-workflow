"""Tests for the bounded artifact reader, version selection and v2 CLI fixture.

Covers SCOUT-002 Task 1: contracts.read_artifact / sha256_file /
validate_evidence / validate_audit, workflow_v2.version / problems, the
V2CLITestCase fixture surface, and the validate/mutate integration of the
version guard (v1 semantics unchanged, v2 structural findings, no State write
on rejected mutation).
"""

import hashlib
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import contracts  # noqa: E402
import workflow_v2  # noqa: E402
from v2_support import (  # noqa: E402
    V2CLITestCase, valid_evidence, valid_audit, CODE_FIXTURE)


class ContractReadTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _path(self, name, text):
        path = os.path.join(self.root, name)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return path

    def _read(self, text, kind="evidence"):
        return contracts.read_artifact(self._path("artifact.md", text), kind)

    def _valid(self):
        return valid_evidence("T1", 1, "c0ffee")

    # -- reader basics ---------------------------------------------------------

    def test_reads_valid_report(self):
        report = self._read(self._valid())
        self.assertEqual(report["metadata"]["artifact_type"], "evidence")
        self.assertEqual(report["metadata"]["round"], 1)
        for name in ("Metadata", "Decision Questions", "Findings",
                     "Unknowns", "Handoff"):
            self.assertIn(name, report["sections"])
        kinds = [(r["id"], r["kind"]) for r in report["records"]]
        self.assertEqual(kinds, [("DQ-01", "question"), ("F-01", "finding")])
        finding = report["records"][1]
        self.assertEqual(finding["tag"], "FACT")
        self.assertIn("main()", finding["fields"]["Statement"])
        self.assertIn("src/app.py:1-2", finding["fields"]["Sources"])

    def test_fenced_headings_are_not_records(self):
        text = self._valid() + (
            "\n```markdown\n"
            "### F-99 [FACT]\n"
            "**Statement:** fenced fake\n"
            "## Fake Section\n"
            "```\n")
        report = self._read(text)
        ids = [r["id"] for r in report["records"]]
        self.assertEqual(ids, ["DQ-01", "F-01"])
        self.assertNotIn("Fake Section", report["sections"])
        self.assertNotIn("F-99", report["sections"]["Handoff"])

    def test_crlf_unicode(self):
        text = self._valid()
        text = text.replace("The entry point is main() in src/app.py.",
                            "入口函数是 main()，位于带空格的路径。")
        text = text.replace("- code: src/app.py:1-2 :: main",
                            "- code: my dir/app.py:1-2 :: main")
        text = text.replace("dirty_changes: []",
                            "dirty_changes:\n  - my dir/app.py")
        report = self._read(text.replace("\n", "\r\n"))
        finding = report["records"][1]
        self.assertIn("入口函数是 main()", finding["fields"]["Statement"])
        self.assertIn("my dir/app.py:1-2", finding["fields"]["Sources"])
        self.assertEqual(report["metadata"]["dirty_changes"], ["my dir/app.py"])

    # -- structural rejections at read time --------------------------------------

    def test_duplicate_dq_id_raises(self):
        text = self._valid().replace("### DQ-01", "### DQ-01\n\n**Question:** x\n\n### DQ-01", 1)
        with self.assertRaises(contracts.ContractError):
            self._read(text)

    def test_duplicate_finding_id_raises(self):
        text = self._valid().replace(
            "## Findings", "## Findings\n\n### F-01 [UNKNOWN]\n\n**Statement:** dup")
        with self.assertRaises(contracts.ContractError):
            self._read(text)

    def test_duplicate_metadata_key_raises(self):
        text = self._valid().replace(
            "round: 1", "round: 1\nround: 2")
        with self.assertRaises(contracts.ContractError):
            self._read(text)

    def test_malformed_metadata_yaml_raises(self):
        text = self._valid().replace("round: 1", "round: [1")
        with self.assertRaises(contracts.ContractError):
            self._read(text)

    def test_missing_metadata_block_raises(self):
        text = self._valid().replace("## Metadata\n\n```yaml\n", "## Metadata\n\n")
        with self.assertRaises(contracts.ContractError):
            self._read(text)

    def test_missing_file_raises(self):
        with self.assertRaises(contracts.ContractError):
            contracts.read_artifact(
                os.path.join(self.root, "absent.md"), "evidence")

    # -- validation problems -------------------------------------------------------

    def _problems(self, text, ticket="T1"):
        report = self._read(text)
        return contracts.validate_evidence(report, ticket)

    def test_valid_report_has_no_problems(self):
        self.assertEqual(self._problems(self._valid()), [])

    def test_dangling_fact_reference(self):
        text = self._valid().replace("**Facts:** F-01", "**Facts:** F-99")
        problems = self._problems(text)
        self.assertTrue(any("F-99" in p for p in problems), problems)

    def test_dangling_question_reference(self):
        text = self._valid().replace("**Questions:** DQ-01", "**Questions:** DQ-99")
        problems = self._problems(text)
        self.assertTrue(any("DQ-99" in p for p in problems), problems)

    def test_missing_code_line_or_symbol(self):
        text = self._valid().replace("- code: src/app.py:1-2 :: main",
                                     "- code: src/app.py")
        problems = self._problems(text)
        self.assertTrue(any("code" in p and ("line" in p or "symbol" in p or "key" in p)
                            for p in problems), problems)

    def test_file_scope_anchor_is_allowed(self):
        text = self._valid().replace("- code: src/app.py:1-2 :: main",
                                     "- code: src/app.py:1-2 :: file scope (no named symbol)")
        self.assertEqual(self._problems(text), [])

    def test_bare_placeholder_rejected(self):
        text = self._valid().replace(
            "**Question:** Which function is the entry point of the fixture?",
            "**Question:** <the question as investigated>")
        problems = self._problems(text)
        self.assertTrue(any("placeholder" in p for p in problems), problems)

    def test_inference_requires_basis(self):
        text = self._valid().replace("### F-01 [FACT]", "### F-01 [INFERENCE]")
        problems = self._problems(text)
        self.assertTrue(any("Basis" in p for p in problems), problems)

    def test_dangling_basis_reference(self):
        text = self._valid().replace("### F-01 [FACT]", "### F-01 [INFERENCE]")
        text = text.replace(
            "**Scope:** the committed fixture only",
            "**Basis:** F-99 supports the inference\n\n"
            "**Scope:** the committed fixture only")
        problems = self._problems(text)
        self.assertTrue(any("Basis" in p and "F-99" in p for p in problems),
                        problems)

    def test_valid_basis_reference_has_no_problem(self):
        text = self._valid().replace("### F-01 [FACT]", "### F-01 [INFERENCE]")
        text = text.replace(
            "**Scope:** the committed fixture only",
            "**Basis:** F-01 supports the inference\n\n"
            "**Scope:** the committed fixture only")
        problems = self._problems(text)
        self.assertFalse(any("Basis" in p for p in problems), problems)

    def test_unknown_answer_with_unknown_fact_link_is_allowed(self):
        text = self._valid().replace("**Answer:** ANSWERED", "**Answer:** UNKNOWN")
        text = text.replace("**Facts:** F-01", "**Facts:** UNKNOWN")
        problems = self._problems(text)
        self.assertFalse(any("Facts" in p for p in problems), problems)

    def test_wrong_ticket_metadata_problem(self):
        problems = self._problems(self._valid(), ticket="T2")
        self.assertTrue(any("ticket" in p.lower() for p in problems), problems)

    def test_missing_required_metadata_problem(self):
        text = self._valid().replace("scout_model: v2-fixture\n", "")
        problems = self._problems(text)
        self.assertTrue(any("scout_model" in p for p in problems), problems)


class ContractAuditTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _report(self, gate="sufficient", round_no=1, sha="ab" * 32):
        path = os.path.join(self.root, "audit.md")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(valid_audit("T1", gate, round_no, sha))
        return contracts.read_artifact(path, "evidence-audit")

    def test_valid_audit_has_no_problems(self):
        report = self._report()
        self.assertEqual(
            contracts.validate_audit(report, "T1", "sufficient", 1), [])
        self.assertEqual(report["records"], [])

    def test_gate_round_mismatch(self):
        report = self._report(gate="sufficient", round_no=1)
        problems = contracts.validate_audit(report, "T1", "insufficient", 1)
        self.assertTrue(any("gate" in p for p in problems), problems)
        problems = contracts.validate_audit(report, "T1", "sufficient", 2)
        self.assertTrue(any("round" in p for p in problems), problems)

    def test_empty_answer_rejected(self):
        report = self._report()
        report["sections"]["What is missing?"] = "\n"
        problems = contracts.validate_audit(report, "T1", "sufficient", 1)
        self.assertTrue(any("What is missing" in p for p in problems), problems)


class Sha256Test(unittest.TestCase):
    def test_raw_bytes_including_line_endings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.md")
            with open(path, "wb") as fh:
                fh.write(b"line1\r\nline2\r\n")
            self.assertEqual(
                contracts.sha256_file(path),
                hashlib.sha256(b"line1\r\nline2\r\n").hexdigest())


class VersionTest(unittest.TestCase):
    def test_missing_version_is_one(self):
        self.assertEqual(workflow_v2.version({}), 1)

    def test_version_two(self):
        self.assertEqual(workflow_v2.version({"workflow_version": 2}), 2)

    def test_invalid_versions_rejected(self):
        for bad in (True, 0, "2", 3):
            with self.subTest(bad=bad):
                with self.assertRaises(contracts.ContractError):
                    workflow_v2.version({"workflow_version": bad})


class ProblemsTest(unittest.TestCase):
    def test_no_problems_for_supported_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(workflow_v2.problems(tmp, {}), [])
            self.assertEqual(workflow_v2.problems(tmp, {"workflow_version": 2}), [])

    def test_future_version_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            problems = workflow_v2.problems(tmp, {"workflow_version": 3})
            self.assertEqual(len(problems), 1)
            self.assertIn("workflow_version", problems[0])

    def test_v2_field_type_problems(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = {"workflow_version": 2,
                    "evidence": {"report_sha256": 42}}
            problems = workflow_v2.problems(tmp, data)
            self.assertTrue(any("report_sha256" in p for p in problems), problems)


class V2FixtureTest(V2CLITestCase):
    def test_seed_v2_sets_version_phase_and_route(self):
        self.seed_v2("evidence_audit")
        data = self.read_state()
        self.assertEqual(data["workflow_version"], 2)
        self.assertEqual(data["phase"], "evidence_audit")
        self.assertEqual(data["next_action"]["role"], "evidence-auditor")
        self.assertEqual(data["evidence"]["gate"], "insufficient")

    def test_write_evidence_is_structurally_valid(self):
        self.seed_v2("evidence_collection")
        path = self.write_evidence()
        report = contracts.read_artifact(path, "evidence")
        self.assertEqual(
            contracts.validate_evidence(report, self.TICKET), [])
        head = self._git("rev-parse", "HEAD").stdout.strip()
        self.assertEqual(report["metadata"]["observed_commit"], head)

    def test_write_audit_is_bound_to_evidence_hash(self):
        self.seed_v2("evidence_audit")
        evidence_path = self.write_evidence()
        audit_path = self.write_audit()
        report = contracts.read_artifact(audit_path, "evidence-audit")
        self.assertEqual(
            contracts.validate_audit(report, self.TICKET, "sufficient", 1), [])
        with open(evidence_path, "rb") as fh:
            self.assertEqual(report["metadata"]["evidence_sha256"],
                             hashlib.sha256(fh.read()).hexdigest())

    def test_capture_files_excludes_git(self):
        files = self.capture_files()
        self.assertIn(os.path.join(".ai", "work", self.TICKET, "state.yaml"),
                      files)
        self.assertTrue(all(".git" not in rel.split(os.sep)[0]
                            for rel in files))

    def test_commit_code_returns_new_head(self):
        before = self._git("rev-parse", "HEAD").stdout.strip()
        head = self.commit_code(os.path.join("src", "new file.py"), "x = 1\n")
        self.assertNotEqual(head, before)
        show = self._git("cat-file", "-e", "%s:%s" % (head, "src/new file.py"))
        self.assertEqual(show.returncode, 0)


class ValidateV2IntegrationTest(V2CLITestCase):
    def test_v2_malformed_evidence_is_error(self):
        self.seed_v2("evidence_audit")
        path = self.write_evidence()
        with open(path, "a", encoding="utf-8", newline="") as fh:
            fh.write("### DQ-01\n\n**Question:** duplicate id\n")
        proc = self.cli("validate")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("ERROR", proc.stdout)
        self.assertIn("evidence.md", proc.stdout)

    def test_v2_scaffold_is_pending_not_error(self):
        self.seed_v2("evidence_collection")
        proc = self.cli("validate")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_v1_ticket_semantics_unchanged(self):
        # v1 ticket, loosely-written evidence: still validates clean.
        with open(os.path.join(self.work, "evidence.md"), "w",
                  encoding="utf-8", newline="") as fh:
            fh.write("## Facts\n- FACT source artifact spec section\n")
        self.assertEqual(self.cli("advance", self.TICKET, "--to",
                                  "evidence_collection").returncode, 0)
        self.assertEqual(self.cli("advance", self.TICKET, "--to",
                                  "evidence_audit").returncode, 0)
        proc = self.cli("validate")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class MutateVersionGuardTest(V2CLITestCase):
    def test_future_version_rejected_without_state_write(self):
        self.seed_v2("requirement")
        data = self.read_state()
        data["workflow_version"] = 3
        self.write_state(data)
        before = self.state_bytes()
        proc = self.cli("advance", self.TICKET, "--to", "evidence_collection")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)


if __name__ == "__main__":
    unittest.main()
