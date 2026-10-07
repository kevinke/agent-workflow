"""Tests for the Review artifact contract and set-review binding (SCOUT-005 T1).

Covers `contracts.validate_review`, `contracts.read_artifact(kind="review")`,
the read-only `review.code_drift` Git assessment, the transactional
`mutate.set_review` command, the additive v2 `review`/`artifacts.review` State
fields, and the set-review CLI. The lifecycle is driven with public commands;
every rejection asserts the State bytes are unchanged.
"""

import hashlib
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import contracts  # noqa: E402
import review  # noqa: E402
from v2_support import V2CLITestCase, valid_plan  # noqa: E402


class ReviewV2Test(V2CLITestCase):
    # -- fixture helpers -----------------------------------------------------

    def _seed_implementation(self, total=1):
        """Reach a ready v2 implementation with a registered `total`-task Plan."""
        self.seed_v2("evidence_audit")
        self.write_evidence(round_no=1)
        self.write_audit(gate="sufficient", round_no=1)
        proc = self.cli("set-gate", self.TICKET, "--gate", "sufficient",
                        "--round", "1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for target in ("technical_decision", "planning"):
            proc = self.cli("advance", self.TICKET, "--to", target)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        plan = self.write_plan(total)
        proc = self.cli("register-plan", self.TICKET, "--path", plan,
                        "--total", str(total))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = self.cli("advance", self.TICKET, "--to", "implementation")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return plan

    def _seed_review(self, total=1, verdict="pass", reviewed_commit=None):
        """Drive the public-command lifecycle into a bind-ready review phase.

        Returns the reviewed commit (the committed, tree-clean HEAD that the
        Review is written against). `decision.md` is written by the senior role
        and committed before that reviewed commit: implementation -> review now
        requires it on a v2 Ticket.
        """
        self._seed_implementation(total)
        self.write_decision()
        # The code under review, committed while in implementation.
        self.commit_code("src/feature.py", "def feature():\n    return 1\n")
        for _ in range(total):
            proc = self.cli("complete-task", self.TICKET,
                            "--total", str(total))
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = self.cli("advance", self.TICKET, "--to", "review")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        # Commit every workflow file so the tree is clean; that HEAD is the
        # reviewed commit the Review binds to.
        self._commit_all("fixture: commit reviewed tree")
        head = self._git("rev-parse", "HEAD").stdout.strip()
        self.write_review(verdict, reviewed_commit=reviewed_commit or head)
        return head

    def _write_file(self, rel, text):
        full = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)

    def _append_file(self, abs_path, text):
        with open(abs_path, "a", encoding="utf-8", newline="") as fh:
            fh.write(text)

    def _commit_all(self, message):
        self.assertEqual(self._git("add", "-A").returncode, 0)
        commit = self._git("commit", "-q", "-m", message)
        self.assertEqual(commit.returncode, 0, commit.stderr)

    def _restore(self, commit):
        """Reset the throwaway repo back to `commit` (fresh reviewed tree)."""
        self.assertEqual(self._git("reset", "--hard", commit).returncode, 0)
        self.assertEqual(self._git("clean", "-fd").returncode, 0)

    def _assert_rejected(self, verdict="pass"):
        before = self.state_bytes()
        proc = self.cli("set-review", self.TICKET, "--verdict", verdict)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def _bind(self, verdict):
        proc = self.cli("set-review", self.TICKET, "--verdict", verdict)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def _append_and_repair(self, total):
        """Append rework up to `total` tasks, then return to implementation."""
        plan = self.write_plan(total)
        proc = self.cli("register-plan", self.TICKET, "--path", plan,
                        "--total", str(total))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = self.cli("advance", self.TICKET, "--to", "implementation")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    # -- happy path ----------------------------------------------------------

    def test_binding_records_artifact_commit_and_plan_identity(self):
        reviewed = self._seed_review()
        proc = self.cli("set-review", self.TICKET, "--verdict", "pass")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        data = self.read_state()
        block = data["review"]
        self.assertEqual(block["verdict"], "pass")
        self.assertEqual(block["reviewed_commit"], reviewed)
        self.assertEqual(block["plan_sha256"],
                         data["source_artifacts"]["plan"]["sha256"])
        with open(os.path.join(self.work, "review.md"), "rb") as fh:
            self.assertEqual(block["artifact_sha256"],
                             hashlib.sha256(fh.read()).hexdigest())
        self.assertEqual(data["artifacts"]["review"], "review.md")

    def test_changes_requested_binds_substantive_review(self):
        self._seed_review(verdict="changes_requested")
        proc = self.cli("set-review", self.TICKET, "--verdict",
                        "changes_requested")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.read_state()["review"]["verdict"],
                         "changes_requested")

    # -- code drift rejections ----------------------------------------------

    def test_code_change_blocks_review_binding(self):
        self._seed_review()
        self.commit_code("src/other_module.py", "def other():\n    return 0\n")
        self._assert_rejected()

    def _drift_committed_test(self):
        self.commit_code("tests/test_added.py", "def test_a():\n    pass\n")

    def _drift_committed_fixture(self):
        self.commit_code("tests/fixtures/sample.json", '{"a": 1}\n')

    def _drift_rename(self):
        self.assertEqual(self._git("mv", "src/feature.py",
                                   "src/renamed_feature.py").returncode, 0)
        self._commit_all("fixture: rename")

    def _drift_deletion(self):
        os.remove(os.path.join(self.root, "src", "feature.py"))
        self._commit_all("fixture: delete")

    def _drift_staged_edit(self):
        self._write_file("src/feature.py", "def feature():\n    return 2\n")
        self.assertEqual(self._git("add", "src/feature.py").returncode, 0)

    def _drift_dirty_edit(self):
        self._write_file("src/feature.py", "def feature():\n    return 3\n")

    def _drift_untracked_test(self):
        self._write_file("tests/test_untracked.py", "def test_u():\n    pass\n")

    def test_drift_variants_block_review_binding(self):
        reviewed = self._seed_review()
        variants = [
            "_drift_committed_test", "_drift_committed_fixture",
            "_drift_rename", "_drift_deletion", "_drift_staged_edit",
            "_drift_dirty_edit", "_drift_untracked_test",
        ]
        for name in variants:
            with self.subTest(variant=name):
                self._restore(reviewed)
                self.write_review("pass", reviewed_commit=reviewed)
                getattr(self, name)()
                self._assert_rejected()

    def test_metadata_only_commit_allows_review_binding(self):
        reviewed = self._seed_review()
        self._append_file(os.path.join(self.work, "progress.md"),
                          "\n- task 1 complete\n")
        self.assertEqual(
            self._git("add", ".ai/work/T1/progress.md").returncode, 0)
        commit = self._git("commit", "-q", "-m", "fixture: progress only")
        self.assertEqual(commit.returncode, 0, commit.stderr)

        proc = self.cli("set-review", self.TICKET, "--verdict", "pass")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.read_state()["review"]["reviewed_commit"],
                         reviewed)

    def test_changed_plan_blocks_review_binding(self):
        reviewed = self._seed_review()
        self._append_file(os.path.join(self.work, "plan.md"),
                          "\n<!-- drifted -->\n")
        self._commit_all("fixture: plan drift")

        drift = review.code_drift(self.root, self.TICKET, reviewed,
                                  ".ai/work/T1/plan.md")
        self.assertTrue(any("Plan" in problem for problem in drift))
        self._assert_rejected()

    # -- artifact / verdict rejections --------------------------------------

    def test_malformed_review_artifact_rejected(self):
        self._seed_review()
        with open(os.path.join(self.work, "review.md"), "w",
                  encoding="utf-8", newline="") as fh:
            fh.write("# Review\n\n## Metadata\n\n```yaml\nartifact_type: review\n"
                     "format_version: 1\nticket_id: T1\n```\n\n## Findings\n\nNone\n")
        self._assert_rejected()

    def test_cli_verdict_mismatch_rejected(self):
        self._seed_review(verdict="pass")
        self._assert_rejected(verdict="changes_requested")

    def test_missing_verdict_is_usage_error(self):
        self._seed_review()
        before = self.state_bytes()
        proc = self.cli("set-review", self.TICKET)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    # -- Git identity --------------------------------------------------------

    def test_code_drift_missing_git_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(contracts.ContractError):
                review.code_drift(tmp, self.TICKET, "deadbeef", "plan.md")

    def test_nonancestor_commit_rejected(self):
        self._seed_review()
        tree = self._git("write-tree").stdout.strip()
        side = self._git("commit-tree", tree, "-m", "unrelated").stdout.strip()
        self.assertTrue(side)
        self.write_review("pass", reviewed_commit=side)
        self._assert_rejected()

    # -- ticket / phase / completeness rejections ---------------------------

    def test_v1_ticket_rejected(self):
        # setUp leaves a fresh v1 ticket in `requirement`.
        self._assert_rejected()

    def test_wrong_phase_rejected(self):
        self.seed_v2("implementation")
        self._assert_rejected()

    def test_incomplete_tasks_rejected(self):
        self._seed_review()
        data = self.read_state()
        data["implementation"]["current_task"] = 0
        data["implementation"]["completed_tasks"] = []
        self.write_state(data)
        self._assert_rejected()

    def test_escalation_blocks_review_binding(self):
        self._seed_review()
        proc = self.cli("escalate", self.TICKET, "--scope", "machine",
                        "--reason", "flagged during review")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self._assert_rejected()

    # -- Unicode / spaced ticket paths --------------------------------------

    def test_unicode_spaced_ticket_path_binds_successfully(self):
        spaced = "T1 步骤"
        self.TICKET = spaced
        self.work = os.path.join(self.root, ".ai", "work", spaced)
        proc = self.cli("start", spaced, "--title", "spaced path ticket")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        self._seed_review()
        proc = self.cli("set-review", spaced, "--verdict", "pass")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.read_state()["review"]["verdict"], "pass")

    # -- v2 routing ----------------------------------------------------------

    def test_review_routes_to_reviewer(self):
        self._seed_review()
        data = self.read_state()
        self.assertEqual(data["next_action"]["role"], "reviewer")

    # -- completion guards: implementation -> review -------------------------

    def test_enter_review_requires_all_tasks_complete(self):
        self._seed_implementation(2)
        self.write_decision()
        self.commit_code("src/feature.py", "def feature():\n    return 1\n")
        self.assertEqual(
            self.cli("complete-task", self.TICKET, "--total", "2").returncode, 0)
        before = self.state_bytes()
        proc = self.cli("advance", self.TICKET, "--to", "review")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_enter_review_requires_decision_artifact(self):
        self._seed_implementation(1)
        # decision.md is deliberately omitted; it is now required before review.
        self.commit_code("src/feature.py", "def feature():\n    return 1\n")
        self.assertEqual(self.cli("complete-task", self.TICKET).returncode, 0)
        before = self.state_bytes()
        proc = self.cli("advance", self.TICKET, "--to", "review")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    # -- completion guards: review -> done -----------------------------------

    def test_done_requires_current_pass(self):
        self._seed_review()  # review.md written but no verdict recorded
        before = self.state_bytes()
        proc = self.cli("advance", self.TICKET, "--to", "done")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_code_change_after_pass_blocks_done(self):
        self._seed_review()
        self._bind("pass")
        self.commit_code("src/other_module.py", "def other():\n    return 0\n")
        before = self.state_bytes()
        proc = self.cli("advance", self.TICKET, "--to", "done")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_review_artifact_change_after_pass_blocks_done(self):
        self._seed_review()
        self._bind("pass")
        self._append_file(os.path.join(self.work, "review.md"),
                          "\n<!-- edited after verdict -->\n")
        before = self.state_bytes()
        proc = self.cli("advance", self.TICKET, "--to", "done")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_workflow_only_commit_still_permits_done(self):
        self._seed_review()
        self._bind("pass")
        self._append_file(os.path.join(self.work, "progress.md"),
                          "\n- task 1 complete\n")
        self.assertEqual(
            self._git("add", ".ai/work/T1/progress.md").returncode, 0)
        commit = self._git("commit", "-q", "-m", "fixture: progress only")
        self.assertEqual(commit.returncode, 0, commit.stderr)

        proc = self.cli("advance", self.TICKET, "--to", "done")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.read_state()["phase"], "done")

    def test_done_is_not_reopened(self):
        self._seed_review()
        self._bind("pass")
        self.assertEqual(
            self.cli("advance", self.TICKET, "--to", "done").returncode, 0)
        attempts = (
            ["advance", self.TICKET, "--to", "review"],
            ["advance", self.TICKET, "--to", "implementation"],
            ["complete-task", self.TICKET],
            ["set-review", self.TICKET, "--verdict", "pass"],
        )
        for args in attempts:
            with self.subTest(cmd=" ".join(args[:2])):
                before = self.state_bytes()
                proc = self.cli(*args)
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertEqual(self.state_bytes(), before)

    # -- append-only repair --------------------------------------------------

    def test_repair_preserves_completed_prefix(self):
        self._seed_review(total=1, verdict="changes_requested")
        self._bind("changes_requested")
        self._append_and_repair(2)

        data = self.read_state()
        self.assertEqual(data["phase"], "implementation")
        self.assertEqual(data["implementation"]["current_task"], 1)
        self.assertEqual(data["implementation"]["completed_tasks"], [1])
        self.assertEqual(data["next_action"]["role"], "ticket-executor")
        self.assertEqual(data["next_action"]["task"], 2)
        self.assertEqual(data["review"]["verdict"], "pending")

        # Execute the appended task, then a fresh passing Review completes it.
        self.commit_code("src/feature2.py", "def feature2():\n    return 2\n")
        self.assertEqual(
            self.cli("complete-task", self.TICKET, "--total", "2").returncode, 0)
        self.assertEqual(
            self.cli("advance", self.TICKET, "--to", "review").returncode, 0)
        self.write_review("pass")
        self._bind("pass")
        proc = self.cli("advance", self.TICKET, "--to", "done")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.read_state()["phase"], "done")

    def test_pass_cannot_repair(self):
        self._seed_review(verdict="pass")
        self._bind("pass")
        before = self.state_bytes()
        proc = self.cli("advance", self.TICKET, "--to", "implementation")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_repair_requires_appended_task(self):
        self._seed_review(verdict="changes_requested")
        self._bind("changes_requested")
        before = self.state_bytes()
        proc = self.cli("advance", self.TICKET, "--to", "implementation")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_repair_rejects_stale_failed_review(self):
        self._seed_review(verdict="changes_requested")
        self._bind("changes_requested")
        plan = self.write_plan(2)
        self.assertEqual(
            self.cli("register-plan", self.TICKET, "--path", plan,
                     "--total", "2").returncode, 0)
        self._append_file(os.path.join(self.work, "review.md"),
                          "\n<!-- edited after verdict -->\n")
        before = self.state_bytes()
        proc = self.cli("advance", self.TICKET, "--to", "implementation")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_repair_rejects_completed_prefix_edit(self):
        self._seed_review(verdict="changes_requested")
        self._bind("changes_requested")
        rel = os.path.join(".ai", "work", self.TICKET, "plan.md")
        changed = valid_plan(self.TICKET, 2).replace(
            "Carry out bounded step 1 for the fixture.",
            "REDESIGNED: do something else entirely.")
        self._write_file(rel, changed)
        before = self.state_bytes()
        proc = self.cli("register-plan", self.TICKET, "--path", rel,
                        "--total", "2")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_second_repair_cycle(self):
        self._seed_review(total=1, verdict="changes_requested")
        self._bind("changes_requested")
        self._append_and_repair(2)

        self.commit_code("src/feature2.py", "def feature2():\n    return 2\n")
        self.assertEqual(
            self.cli("complete-task", self.TICKET, "--total", "2").returncode, 0)
        self.assertEqual(
            self.cli("advance", self.TICKET, "--to", "review").returncode, 0)
        self.write_review("changes_requested")
        self._bind("changes_requested")
        self._append_and_repair(3)

        data = self.read_state()
        self.assertEqual(data["implementation"]["current_task"], 2)
        self.assertEqual(data["implementation"]["completed_tasks"], [1, 2])
        self.assertEqual(data["next_action"]["task"], 3)
        self.assertEqual(data["review"]["verdict"], "pending")

    def test_escalation_blocks_repair(self):
        self._seed_review(verdict="changes_requested")
        self._bind("changes_requested")
        plan = self.write_plan(2)
        self.assertEqual(
            self.cli("register-plan", self.TICKET, "--path", plan,
                     "--total", "2").returncode, 0)
        self.assertEqual(
            self.cli("escalate", self.TICKET, "--scope", "machine",
                     "--reason", "design change needs a senior").returncode, 0)
        before = self.state_bytes()
        proc = self.cli("advance", self.TICKET, "--to", "implementation")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    # -- validate agreement --------------------------------------------------

    def test_validate_reports_done_without_pass(self):
        self._seed_review()  # no verdict recorded
        data = self.read_state()
        data["phase"] = "done"
        data["next_action"] = {"role": None, "action": None, "task": None}
        self.write_state(data)
        proc = self.cli("validate", self.TICKET)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("review.verdict", proc.stdout)

    def test_validate_reports_stale_pass_binding(self):
        self._seed_review()
        self._bind("pass")
        self._append_file(os.path.join(self.work, "review.md"),
                          "\n<!-- edited after verdict -->\n")
        proc = self.cli("validate", self.TICKET)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("Review artifact changed", proc.stdout)

    def test_validate_accepts_repair_intermediate_state(self):
        self._seed_review(total=1, verdict="changes_requested")
        self._bind("changes_requested")
        self._append_and_repair(2)
        proc = self.cli("validate", self.TICKET)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("validate: OK", proc.stdout)


if __name__ == "__main__":
    unittest.main()