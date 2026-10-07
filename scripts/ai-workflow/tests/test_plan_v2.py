"""Tests for the registered execution Plan contract (SCOUT-003 Task 1).

Covers contracts.read_plan (the Plan grammar/reader), the register-plan CLI
command and mutate.register_plan transaction, the additive v2 State fields
(source_artifacts.plan.path/sha256, implementation.task_hashes) and the
protocol rejections that keep a rejected mutation from touching State bytes.
"""

import hashlib
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import contracts  # noqa: E402
from v2_support import V2CLITestCase, valid_plan  # noqa: E402


class PlanV2Test(V2CLITestCase):
    # -- fixture helpers -----------------------------------------------------

    def _seed_planning(self):
        """Reach a coherent planning phase with a current, bound audit."""
        self.seed_v2("evidence_audit")
        self.write_evidence(round_no=1)
        self.write_audit(gate="sufficient", round_no=1)
        proc = self.cli("set-gate", self.TICKET, "--gate", "sufficient",
                        "--round", "1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for target in ("technical_decision", "planning"):
            proc = self.cli("advance", self.TICKET, "--to", target)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def _write_plan_text(self, text, name="plan.md"):
        full = os.path.join(self.work, name)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return os.path.relpath(full, self.root)

    def _register(self, path, total):
        return self.cli("register-plan", self.TICKET, "--path", path,
                        "--total", str(total))

    # -- happy path ----------------------------------------------------------

    def test_register_one_task_stores_plan_and_hashes(self):
        self._seed_planning()
        rel = self.write_plan(1)
        proc = self._register(rel, 1)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        data = self.read_state()
        plan_ref = data["source_artifacts"]["plan"]
        self.assertEqual(plan_ref["path"], rel)
        with open(os.path.join(self.root, rel), "rb") as fh:
            self.assertEqual(plan_ref["sha256"],
                             hashlib.sha256(fh.read()).hexdigest())

        impl = data["implementation"]
        self.assertEqual(impl["total_tasks"], 1)
        self.assertEqual(impl["current_task"], 0)
        self.assertEqual(impl["completed_tasks"], [])
        tasks = contracts.read_plan(os.path.join(self.root, rel), self.TICKET)
        self.assertEqual([t["number"] for t in tasks], [1])
        self.assertEqual(impl["task_hashes"], [tasks[0]["sha256"]])

    def test_unicode_space_path_accepted(self):
        self._seed_planning()
        rel = self.write_plan(1, name=os.path.join("my plans", "步骤 plan.md"))
        proc = self._register(rel, 1)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.read_state()["source_artifacts"]["plan"]["path"],
                         rel)

    # -- reader / grammar rejections ----------------------------------------

    def test_missing_plan_file_rejected(self):
        self._seed_planning()
        before = self.state_bytes()
        proc = self._register(os.path.join(".ai", "work", self.TICKET,
                                           "absent.md"), 1)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_missing_field_rejected(self):
        self._seed_planning()
        text = valid_plan(self.TICKET, 1).replace(
            "### Invariants\nmain() keeps returning 42.\n\n", "")
        rel = self._write_plan_text(text)
        before = self.state_bytes()
        proc = self._register(rel, 1)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_declared_count_mismatch_rejected(self):
        self._seed_planning()
        rel = self.write_plan(1)
        before = self.state_bytes()
        proc = self._register(rel, 2)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_noncontiguous_task_numbers_rejected(self):
        self._seed_planning()
        text = valid_plan(self.TICKET, 2).replace("## Task 2", "## Task 3")
        rel = self._write_plan_text(text)
        before = self.state_bytes()
        proc = self._register(rel, 2)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_forward_dependency_rejected(self):
        self._seed_planning()
        text = valid_plan(self.TICKET, 2).replace("N/A (first task)", "Task 2")
        rel = self._write_plan_text(text)
        before = self.state_bytes()
        proc = self._register(rel, 2)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_self_dependency_rejected(self):
        self._seed_planning()
        text = valid_plan(self.TICKET, 2).replace("N/A (first task)", "Task 1")
        rel = self._write_plan_text(text)
        before = self.state_bytes()
        proc = self._register(rel, 2)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    # -- path bounding -------------------------------------------------------

    def test_outside_root_path_rejected(self):
        self._seed_planning()
        outside = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        target = os.path.join(outside, "plan.md")
        with open(target, "w", encoding="utf-8", newline="") as fh:
            fh.write(valid_plan(self.TICKET, 1))
        rel = os.path.relpath(target, self.root)
        before = self.state_bytes()
        proc = self._register(rel, 1)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_symlink_escape_rejected(self):
        self._seed_planning()
        outside = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        target = os.path.join(outside, "plan.md")
        with open(target, "w", encoding="utf-8", newline="") as fh:
            fh.write(valid_plan(self.TICKET, 1))
        link = os.path.join(self.work, "linked-plan.md")
        try:
            os.symlink(target, link)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not available in this environment")
        rel = os.path.relpath(link, self.root)
        before = self.state_bytes()
        proc = self._register(rel, 1)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    # -- CLI / phase / version semantics ------------------------------------

    def test_invalid_total_is_usage_error(self):
        self._seed_planning()
        rel = self.write_plan(1)
        before = self.state_bytes()
        proc = self._register(rel, "abc")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertNotIn("unknown command", proc.stderr)
        self.assertIn("total", proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_v1_ticket_rejected(self):
        rel = self.write_plan(1)  # setUp leaves a fresh v1 ticket
        before = self.state_bytes()
        proc = self._register(rel, 1)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_wrong_phase_rejected(self):
        self.seed_v2("implementation")
        rel = self.write_plan(1)
        before = self.state_bytes()
        proc = self._register(rel, 1)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    # -- re-registration / append -------------------------------------------

    def test_reregistration_preserves_completed_prefix(self):
        self._seed_planning()
        rel = self.write_plan(2)
        self.assertEqual(self._register(rel, 2).returncode, 0)
        self.assertEqual(
            self.cli("complete-task", self.TICKET).returncode, 0)

        before = self.read_state()["implementation"]
        proc = self._register(rel, 2)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        after = self.read_state()["implementation"]
        self.assertEqual(after["current_task"], 1)
        self.assertEqual(after["completed_tasks"], [1])
        self.assertEqual(after["task_hashes"], before["task_hashes"])

    def test_rewritten_completed_contract_rejected(self):
        self._seed_planning()
        rel = self.write_plan(2)
        self.assertEqual(self._register(rel, 2).returncode, 0)
        self.assertEqual(
            self.cli("complete-task", self.TICKET).returncode, 0)

        changed = valid_plan(self.TICKET, 2).replace(
            "Carry out bounded step 1 for the fixture.",
            "REDESIGNED: do something else entirely.")
        self._write_plan_text(changed, name="plan.md")
        before = self.state_bytes()
        proc = self._register(rel, 2)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_review_rework_must_strictly_append(self):
        self.seed_v2("review")
        data = self.read_state()
        rel = self.write_plan(1)
        digest = contracts.sha256_file(os.path.join(self.root, rel))
        tasks = contracts.read_plan(os.path.join(self.root, rel), self.TICKET)
        data["review"] = {"verdict": "changes_requested"}
        data["source_artifacts"]["plan"] = {"path": rel, "sha256": digest}
        data["implementation"] = {"current_task": 1, "total_tasks": 1,
                                  "completed_tasks": [1],
                                  "task_hashes": [tasks[0]["sha256"]]}
        self.write_state(data)

        self.write_plan(2)  # strictly appended rework
        proc = self._register(rel, 2)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.read_state()["implementation"]["total_tasks"], 2)

        self.write_plan(1)  # not an append: rejected
        before = self.state_bytes()
        proc = self._register(rel, 1)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)


if __name__ == "__main__":
    unittest.main()