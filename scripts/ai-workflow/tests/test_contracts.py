"""Tests for the bounded artifact reader, version selection and v2 CLI fixture.

Covers SCOUT-002 Task 1: contracts.read_artifact / sha256_file /
validate_evidence / validate_audit, workflow_v2.version / problems, the
V2CLITestCase fixture surface, and the validate/mutate integration of the
version guard (v1 semantics unchanged, v2 structural findings, no State write
on rejected mutation).
"""

import hashlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import contracts  # noqa: E402
import workflow_v2  # noqa: E402
from v2_support import (  # noqa: E402
    V2CLITestCase, valid_evidence, valid_audit, valid_review, CODE_FIXTURE)


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
        # 7+ hex: the minimum concrete observed_commit abbreviation (Task 1).
        return valid_evidence("T1", 1, "c0ffee0")

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

    def test_answered_question_requires_a_fact_id(self):
        text = self._valid().replace("**Facts:** F-01", "**Facts:** trust me")
        problems = self._problems(text)
        self.assertTrue(any("ANSWERED" in p and "Facts" in p for p in problems),
                        problems)

    def test_finding_requires_a_question_reference(self):
        text = self._valid().replace("**Questions:** DQ-01",
                                     "**Questions:** the entry point question")
        problems = self._problems(text)
        self.assertTrue(any("Questions" in p for p in problems), problems)

    def test_inference_basis_requires_a_fact_id(self):
        text = self._valid().replace("### F-01 [FACT]", "### F-01 [INFERENCE]")
        text = text.replace(
            "**Scope:** the committed fixture only",
            "**Basis:** trust me, the layout is obvious\n\n"
            "**Scope:** the committed fixture only")
        problems = self._problems(text)
        self.assertTrue(any("Basis" in p for p in problems), problems)

    def test_dangling_inference_basis_source_rejected(self):
        text = self._valid().replace(
            "- code: src/app.py:1-2 :: main",
            "- inference basis: F-99")
        problems = self._problems(text)
        self.assertTrue(any("F-99" in p for p in problems), problems)

    def test_missing_code_line_or_symbol(self):
        text = self._valid().replace("- code: src/app.py:1-2 :: main",
                                     "- code: src/app.py")
        problems = self._problems(text)
        self.assertTrue(any("code" in p and ("line" in p or "symbol" in p or "key" in p)
                            for p in problems), problems)

    def test_file_scope_anchor_is_allowed(self):
        text = self._valid().replace("- code: src/app.py:1-2 :: main",
                                     "- code: src/app.py:1-2 :: file scope "
                                     "(reason: no named symbol at module level)")
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

    # -- concrete metadata rules (HARDEN-005 Task 1) -----------------------------

    def test_boolean_round_rejected(self):
        text = self._valid().replace("round: 1", "round: true")
        self.assertTrue(self._problems(text))

    def test_string_round_rejected(self):
        text = self._valid().replace("round: 1", 'round: "1"')
        self.assertTrue(self._problems(text))

    def test_zero_round_rejected(self):
        text = self._valid().replace("round: 1", "round: 0")
        self.assertTrue(self._problems(text))

    def test_observed_commit_must_be_hex_7_to_64(self):
        for bad in ("deadgbe", "c0ffee", "0" * 65):
            with self.subTest(commit=bad):
                text = self._valid().replace(
                    "observed_commit: c0ffee0", "observed_commit: %s" % bad)
                problems = self._problems(text)
                self.assertTrue(any("observed_commit" in p for p in problems),
                                problems)
        for good in ("c0ffee0", "abcdef0", "b" * 40, "f" * 64):
            with self.subTest(commit=good):
                text = self._valid().replace(
                    "observed_commit: c0ffee0", "observed_commit: %s" % good)
                self.assertFalse(
                    any("observed_commit" in p for p in self._problems(text)))

    def test_placeholder_harness_or_model_rejected(self):
        for key in ("scout_harness", "scout_model"):
            with self.subTest(key=key):
                text = self._valid().replace(
                    "%s: v2-fixture" % key, "%s: <pending>" % key)
                problems = self._problems(text)
                self.assertTrue(any(key in p for p in problems), problems)

    def test_created_at_must_be_iso8601(self):
        for bad in ("banana", "2026-13-45", "07/10/2026", ""):
            with self.subTest(created_at=bad):
                text = self._valid().replace(
                    "created_at: 2026-10-07T00:00:00+00:00",
                    "created_at: %s" % bad)
                problems = self._problems(text)
                self.assertTrue(any("created_at" in p for p in problems),
                                problems)

    def test_created_at_timestamp_aliases_stay_valid(self):
        for value in ("2026-10-07T00:00:00+00:00", "2026-10-07",
                      "2026-10-07T12:30:00Z", "2026-10-07T12:30:00"):
            with self.subTest(created_at=value):
                text = self._valid().replace(
                    "created_at: 2026-10-07T00:00:00+00:00",
                    "created_at: %s" % value)
                self.assertFalse(
                    any("created_at" in p for p in self._problems(text)))


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

    def test_audit_round_must_be_positive_integer(self):
        for bad in ("banana", "true", '"1"', "0", "-1"):
            with self.subTest(round=bad):
                text = valid_audit("T1", "sufficient", 1, "ab" * 32)
                text = text.replace("round: 1", "round: %s" % bad, 1)
                path = os.path.join(self.root, "audit.md")
                with open(path, "w", encoding="utf-8", newline="") as fh:
                    fh.write(text)
                report = contracts.read_artifact(path, "evidence-audit")
                problems = contracts.validate_audit(report, "T1",
                                                    "sufficient", 1)
                self.assertTrue(any("round" in p for p in problems), problems)

    def test_empty_answer_rejected(self):
        report = self._report()
        report["sections"]["What is missing?"] = "\n"
        problems = contracts.validate_audit(report, "T1", "sufficient", 1)
        self.assertTrue(any("What is missing" in p for p in problems), problems)


class SourceProblemsTest(unittest.TestCase):
    """Pure syntax boundary of contracts.source_problems (HARDEN-005 Task 1).

    No Git access, no file existence, no truth judgments: family prefix,
    line ranges, anchors and labels only.
    """

    def test_code_source_boundary_assertions(self):
        self.assertTrue(contracts.source_problems("code: src/app.py :: main", "FACT"))
        self.assertTrue(contracts.source_problems("code: src/app.py:1-2", "FACT"))
        self.assertEqual(contracts.source_problems("code: src/app.py:1-2 :: main", "FACT"), [])

    def test_zero_and_reversed_line_ranges_rejected(self):
        for bad in ("code: src/app.py:0 :: main",
                    "code: src/app.py:0-0 :: main",
                    "code: src/app.py:5-3 :: main",
                    "code: src/app.py:12-0 :: main"):
            with self.subTest(source=bad):
                self.assertTrue(contracts.source_problems(bad, "FACT"), bad)

    def test_paths_with_spaces_are_accepted(self):
        self.assertEqual(
            contracts.source_problems("code: my dir/app.py:1-2 :: main", "FACT"),
            [])

    def test_justified_file_scope_anchor_is_accepted(self):
        self.assertEqual(
            contracts.source_problems(
                "code: src/app.py:1-2 :: file scope (reason: no named symbol)",
                "FACT"),
            [])

    def test_unjustified_file_scope_anchor_rejected(self):
        for anchor in ("file scope", "file scope (no named symbol)",
                       "file scope (reason: )"):
            with self.subTest(anchor=anchor):
                source = "code: src/app.py:1-2 :: %s" % anchor
                self.assertTrue(contracts.source_problems(source, "FACT"),
                                source)

    def test_config_and_data_follow_the_code_shape(self):
        self.assertEqual(
            contracts.source_problems("config: conf/app.ini:3-4 :: cache.ttl",
                                      "FACT"), [])
        self.assertEqual(
            contracts.source_problems("data: data/roster.csv:8 :: row[42]",
                                      "FACT"), [])
        self.assertTrue(contracts.source_problems("config: conf/app.ini", "FACT"))
        self.assertTrue(contracts.source_problems("data: data/roster.csv :: row", "FACT"))

    def test_runtime_field_aliases_accepted(self):
        self.assertEqual(
            contracts.source_problems(
                "runtime: python app.py / input: none / observed result: 42"
                " / exit status: 0", "FACT"),
            [])
        self.assertEqual(
            contracts.source_problems(
                'runtime: python app.py / input: --json flag / result: {"v": 42}'
                " / exit: 0", "FACT"),
            [])

    def test_runtime_missing_or_non_integer_fields_rejected(self):
        for bad in ("runtime: python app.py / observed result: 42 / exit: 0",
                    "runtime: python app.py / input: none / exit: 0",
                    "runtime: python app.py / input: none / result: 42",
                    "runtime: python app.py / input: none / result: 42 / exit: zero",
                    "runtime: / input: none / result: 42 / exit: 0"):
            with self.subTest(source=bad):
                self.assertTrue(contracts.source_problems(bad, "FACT"), bad)

    def test_negative_search_requires_scope_exclusions_result(self):
        good = ("negative search: scope src/*.py for callers of main"
                " / exclusions: none / result: no matches")
        self.assertEqual(contracts.source_problems(good, "FACT"), [])
        for bad in ("negative search: src/*.py for callers / exclusions: none"
                    " / result: no matches",
                    "negative search: scope src/*.py / result: no matches",
                    "negative search: scope src/*.py / exclusions: none"):
            with self.subTest(source=bad):
                self.assertTrue(contracts.source_problems(bad, "FACT"), bad)

    def test_inference_basis_requires_fact_ids(self):
        self.assertEqual(
            contracts.source_problems("inference basis: F-01, F-02",
                                      "INFERENCE"), [])
        self.assertTrue(
            contracts.source_problems("inference basis: trust me", "INFERENCE"))
        self.assertTrue(contracts.source_problems("inference basis:", "INFERENCE"))

    def test_unknown_source_needs_unobserved_item_and_collection_target(self):
        self.assertEqual(
            contracts.source_problems(
                "unknown: external callers of main()"
                " / collect at: consuming repository search", "UNKNOWN"),
            [])
        self.assertEqual(
            contracts.source_problems(
                "unknown: external callers of main()"
                " / collection target: consuming repository search", "UNKNOWN"),
            [])
        self.assertTrue(
            contracts.source_problems(
                "unknown: depends on the intended contract", "UNKNOWN"))

    def test_unknown_source_only_on_unknown_findings(self):
        self.assertTrue(
            contracts.source_problems(
                "unknown: external callers / collect at: repo search", "FACT"))
        self.assertTrue(
            contracts.source_problems(
                "unknown: external callers / collect at: repo search",
                "INFERENCE"))

    def test_unrecognised_families_rejected(self):
        for bad in ("trust me", "sources: somewhere", "code src/app.py:1-2 :: main",
                    "code:", "", "code:  "):
            with self.subTest(source=bad):
                self.assertTrue(contracts.source_problems(bad, "FACT"), bad)


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
        # v1 ticket, loosely-written evidence: still validates clean. setUp's
        # `start` now yields v2, so the v1 version is seeded explicitly.
        self.seed_v1("requirement")
        with open(os.path.join(self.work, "evidence.md"), "w",
                  encoding="utf-8", newline="") as fh:
            fh.write("## Facts\n- FACT source artifact spec section\n")
        self.assertEqual(self.cli("advance", self.TICKET, "--to",
                                  "evidence_collection").returncode, 0)
        self.assertEqual(self.cli("advance", self.TICKET, "--to",
                                  "evidence_audit").returncode, 0)
        proc = self.cli("validate")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


PROVENANCE_KEYS = ("format_version", "reviewed_commit", "context_sha256",
                   "live_manifest_sha256", "snapshot_manifest_sha256",
                   "plan_sha256", "input_hashes", "boundary", "runs",
                   "probe_changes", "residual_changes", "limits")

_HEX = hashlib.sha256(b"identity").hexdigest()
_OID = "d" * 40


def _valid_provenance():
    """A shape-valid reserved provenance declaration (values are not checked
    here: `read_review_provenance` establishes conformance, never truth)."""
    return {
        "format_version": 1,
        "reviewed_commit": _OID,
        "context_sha256": _HEX,
        "live_manifest_sha256": _HEX,
        "snapshot_manifest_sha256": _HEX,
        "plan_sha256": _HEX,
        "input_hashes": {".ai/work/T1/decision.md": _HEX},
        "boundary": {
            "profile": "linux-bwrap-v1",
            "enforced": True,
            "preflight": "meta/preflight.json",
            "preflight_sha256": _HEX,
        },
        "runs": [{
            "run_id": "a" * 32,
            "kind": "baseline",
            "argv": ["python3", "-m", "pytest"],
            "exit_code": 0,
            "stdout_sha256": _HEX,
            "stderr_sha256": _HEX,
            "snapshot_before": _HEX,
            "snapshot_after": _HEX,
        }],
        "probe_changes": [{
            "path": "src/app.py",
            "before_sha256": _HEX,
            "after_sha256": None,
            "deleted": True,
        }],
        "residual_changes": {"modified": [], "added": [],
                             "removed": ["src/app.py"]},
        "limits": ["Only the quoted command was executed."],
    }


def _provenance_section(claim=None):
    claim = _valid_provenance() if claim is None else claim
    return ("\n## Isolation provenance\n\n```json\n%s\n```\n"
            % json.dumps(claim, indent=2, sort_keys=True))


class ParseArtifactTest(unittest.TestCase):
    """`parse_artifact` is `read_artifact`'s body: same shape, same results."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.artifacts = {
            "evidence": valid_evidence("T1", 1, "abc1234"),
            "evidence-audit": valid_audit("T1", "sufficient", 1, _HEX),
            "review": valid_review("T1", "pass", "abc1234", _HEX),
        }

    def tearDown(self):
        self._tmp.cleanup()

    def _path(self, kind, text):
        path = os.path.join(self.root, "%s.md" % kind)
        with open(path, "wb") as fh:
            fh.write(text.encode("utf-8"))
        return path

    def test_parse_matches_read_for_every_kind(self):
        for kind, text in self.artifacts.items():
            with self.subTest(kind=kind):
                raw = text.encode("utf-8")
                parsed = contracts.parse_artifact(raw, kind)
                self.assertEqual(parsed, contracts.read_artifact(self._path(
                    kind, text), kind))
                self.assertEqual(sorted(parsed), ["metadata", "records",
                                                 "sections"])

    def test_crlf_and_unicode_bytes_parse_identically(self):
        text = self.artifacts["review"].replace("\n", "\r\n") + "é\n"
        raw = text.encode("utf-8")
        path = self._path("review", text)
        self.assertEqual(contracts.parse_artifact(raw, "review"),
                         contracts.read_artifact(path, "review"))
        self.assertIn(b"\r\n", raw, "the fixture lost its CRLF")

    def test_unknown_kind_is_rejected_from_bytes_and_disk(self):
        raw = self.artifacts["review"].encode("utf-8")
        with self.assertRaises(contracts.ContractError) as ctx:
            contracts.parse_artifact(raw, "notes")
        self.assertIn("unknown artifact kind", str(ctx.exception))
        with self.assertRaises(contracts.ContractError):
            contracts.read_artifact(self._path("review",
                                               self.artifacts["review"]),
                                    "notes")

    def test_non_utf8_bytes_and_missing_file_report_as_contract_errors(self):
        with self.assertRaises(contracts.ContractError) as ctx:
            contracts.parse_artifact(b"\xff\xfe not utf-8", "review")
        self.assertIn("not UTF-8", str(ctx.exception))
        with self.assertRaises(contracts.ContractError):
            contracts.read_artifact(os.path.join(self.root, "absent.md"),
                                    "review")

    def test_fenced_heading_is_still_not_a_record_boundary(self):
        text = self.artifacts["evidence"] + (
            "```markdown\n### F-99 [FACT]\n\n**Statement:** fake\n```\n")
        self.assertEqual(contracts.validate_evidence(
            contracts.parse_artifact(text.encode("utf-8"), "evidence"), "T1"),
            [])


class ReviewProvenanceTest(unittest.TestCase):
    """The reserved `Isolation provenance` section: absent, exact or refused."""

    def _raw(self, section=""):
        return (valid_review("T1", "pass", "abc1234", _HEX) + section).encode(
            "utf-8")

    def test_absent_section_is_a_legacy_report(self):
        self.assertIsNone(contracts.read_review_provenance(self._raw()))

    def test_a_heading_only_inside_a_code_fence_is_not_a_section(self):
        fenced = "\n```\n## Isolation provenance\n\n```json\n{}\n```\n```\n"
        self.assertIsNone(contracts.read_review_provenance(self._raw(fenced)))

    def test_declared_section_parses_to_the_exact_mapping(self):
        claim = _valid_provenance()
        parsed = contracts.read_review_provenance(self._raw(
            _provenance_section(claim)))
        self.assertEqual(parsed, claim)
        self.assertEqual(sorted(parsed), sorted(PROVENANCE_KEYS))

    def test_duplicate_section_raises(self):
        with self.assertRaises(contracts.ContractError) as ctx:
            contracts.read_review_provenance(self._raw(
                _provenance_section() + _provenance_section()))
        self.assertIn("duplicate", str(ctx.exception).lower())

    def test_two_fences_in_one_section_raises(self):
        section = ("\n## Isolation provenance\n\n```json\n%s\n```\n\n"
                   "```json\n%s\n```\n"
                   % (json.dumps(_valid_provenance()),
                      json.dumps(_valid_provenance())))
        with self.assertRaises(contracts.ContractError) as ctx:
            contracts.read_review_provenance(self._raw(section))
        self.assertIn("exactly one", str(ctx.exception))

    def test_no_fence_at_all_raises(self):
        with self.assertRaises(contracts.ContractError):
            contracts.read_review_provenance(self._raw(
                "\n## Isolation provenance\n\nSee the attached log.\n"))

    def test_malformed_and_non_object_json_raise(self):
        for body in ("{not json}", "[1, 2, 3]", '"a string"', "null", "17"):
            with self.subTest(body=body):
                with self.assertRaises(contracts.ContractError):
                    contracts.read_review_provenance(
                        self._raw("\n## Isolation provenance\n\n```json\n%s\n"
                                  "```\n" % body))

    def test_every_missing_required_field_raises(self):
        for key in PROVENANCE_KEYS:
            with self.subTest(missing=key):
                claim = _valid_provenance()
                del claim[key]
                with self.assertRaises(contracts.ContractError) as ctx:
                    contracts.read_review_provenance(self._raw(
                        _provenance_section(claim)))
                self.assertIn(key, str(ctx.exception))

    def test_undeclared_extra_field_raises(self):
        claim = _valid_provenance()
        claim["model_seniority"] = "claimed senior"
        with self.assertRaises(contracts.ContractError) as ctx:
            contracts.read_review_provenance(self._raw(_provenance_section(claim)))
        self.assertIn("model_seniority", str(ctx.exception))

    def test_wrong_typed_and_partial_declarations_raise(self):
        for key, value in (
                ("format_version", "1"), ("format_version", 2),
                ("format_version", True),
                ("reviewed_commit", "abc1234"),
                ("reviewed_commit", "D" * 40),
                ("plan_sha256", _HEX.upper()),
                ("plan_sha256", "short"),
                ("input_hashes", {}),
                ("input_hashes", [_HEX]),
                ("input_hashes", {"/abs/decision.md": _HEX}),
                ("input_hashes", {"../escape.md": _HEX}),
                ("input_hashes", {"a.md": "not-a-hash"}),
                ("boundary", "linux-bwrap-v1"),
                ("boundary", {"profile": "linux-bwrap-v1"}),
                ("boundary", dict(_valid_provenance()["boundary"],
                                  enforced="yes")),
                ("runs", []),
                ("runs", [{"run_id": "a"}]),
                ("runs", [dict(_valid_provenance()["runs"][0], kind="smoke")]),
                ("runs", [dict(_valid_provenance()["runs"][0], argv="pytest")]),
                ("runs", [dict(_valid_provenance()["runs"][0],
                               exit_code=True)]),
                ("probe_changes", "src/app.py"),
                ("probe_changes", [{"path": "/abs/src/app.py"}]),
                ("probe_changes", [{"path": "src/app.py",
                                    "before_sha256": _HEX}]),
                ("residual_changes", ["src/app.py"]),
                ("residual_changes", {"modified": [], "added": []}),
                ("residual_changes", {"modified": "src/app.py", "added": [],
                                      "removed": []}),
                ("limits", []),
                ("limits", [""]),
                ("limits", "only one limit")):
            with self.subTest(key=key, value=repr(value)[:40]):
                claim = _valid_provenance()
                claim[key] = value
                with self.assertRaises(contracts.ContractError) as ctx:
                    contracts.read_review_provenance(self._raw(
                        _provenance_section(claim)))
                self.assertIn(key, str(ctx.exception))

    def test_a_restored_probe_edit_is_a_legal_declaration(self):
        claim = _valid_provenance()
        claim["probe_changes"] = [{"path": "src/app.py", "before_sha256": _HEX,
                                   "after_sha256": _HEX, "deleted": False}]
        claim["residual_changes"] = {"modified": [], "added": [], "removed": []}
        self.assertEqual(contracts.read_review_provenance(
            self._raw(_provenance_section(claim))), claim)


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
