"""Tests for v2 effective escalation routing (SCOUT-004 Task 1).

Drives the real CLI against the V2CLITestCase fixture: escalating a v2 ticket
atomically records the interrupted continuation, sets status=escalation_required
and routes next_action to the phase's senior resolver; routine advance/completion
and a raw status overwrite are rejected until a checked `escalate --clear
--resolution` records the senior resolution and restores the phase-appropriate
action and previous status. Every rejection leaves the raw State bytes untouched,
and v1 semantics stay byte-compatible.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from v2_support import V2CLITestCase, valid_plan  # noqa: E402

RESOLUTION = "resolved per decision.md and F-01"


class EscalationV2Test(V2CLITestCase):
    # -- fixture helpers -----------------------------------------------------

    def _escalate(self, scope="machine", reason="unresolved design"):
        return self.cli("escalate", self.TICKET, "--scope", scope,
                        "--reason", reason)

    def _clear(self, resolution=RESOLUTION):
        args = ["escalate", self.TICKET, "--clear"]
        if resolution is not None:
            args += ["--resolution", resolution]
        return self.cli(*args)

    def _seed_planning(self):
        """Reach a coherent planning phase through the public commands."""
        self.seed_v2("evidence_audit")
        self.write_evidence(round_no=1)
        self.write_audit(gate="sufficient", round_no=1)
        proc = self.cli("set-gate", self.TICKET, "--gate", "sufficient",
                        "--round", "1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for target in ("technical_decision", "planning"):
            proc = self.cli("advance", self.TICKET, "--to", target)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def _seed_implementation(self, total=1):
        """Reach a genuinely execution-ready v2 implementation.

        The phase's decision.md is part of the ready state: a recovery clear
        requires every retained-phase artifact before the continuation is
        restored, so the fixture records it here.
        """
        self._seed_planning()
        rel = self.write_plan(total)
        proc = self.cli("register-plan", self.TICKET, "--path", rel,
                        "--total", str(total))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = self.cli("advance", self.TICKET, "--to", "implementation")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.write_decision()

    def _escalated_implementation(self, total=1):
        """A clean ready implementation, escalated into ordinary recovery.

        seed_v2 never clears the escalation block (nor counter/upgrade
        residue), so each recovery case resets those first: a rejected clear
        in an earlier case must not poison the next one.
        """
        self._reset_recovery_residue()
        self._seed_implementation(total)
        self.assertEqual(self._escalate().returncode, 0)

    def _reset_recovery_residue(self):
        """Reset the recovery-related blocks seed_v2 leaves untouched."""
        data = self.read_state()
        data["escalation"] = {"required": False, "scope": "machine",
                              "reason": None}
        data["implementation"] = {"current_task": 0, "total_tasks": 0,
                                  "completed_tasks": [], "task_hashes": []}
        data.pop("upgrade", None)
        data.pop("migration", None)
        data.pop("adoption_checkpoint", None)
        self.write_state(data)

    # -- step 1: routing failure + completion block --------------------------

    def test_machine_escalation_changes_route_and_blocks_completion(self):
        self.seed_v2("implementation")
        self.assertEqual(self.cli("escalate", "T1", "--scope", "machine",
                                  "--reason", "unresolved design").returncode, 0)
        data = self.read_state()
        self.assertEqual(data["status"], "escalation_required")
        self.assertEqual(data["next_action"]["role"], "technical-decision")
        before = self.state_bytes()
        result = self.cli("complete-task", "T1", "--total", "1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("escalation", result.stderr.lower())
        self.assertEqual(self.state_bytes(), before)

    # -- phase-to-resolver routing (spec decision 5) -------------------------

    def test_phase_to_resolver_routing(self):
        table = [
            ("requirement", "workflow-bootstrap"),
            ("evidence_collection", "evidence-auditor"),
            ("evidence_audit", "evidence-auditor"),
            ("followup_evidence", "evidence-auditor"),
            ("technical_decision", "technical-decision"),
            ("planning", "technical-decision"),
            ("implementation", "technical-decision"),
            ("review", "technical-decision"),
        ]
        for phase, role in table:
            with self.subTest(phase=phase):
                self.seed_v2(phase)
                self.assertEqual(self._escalate().returncode, 0)
                data = self.read_state()
                self.assertEqual(data["status"], "escalation_required")
                self.assertEqual(data["next_action"]["role"], role)
                self.assertIsNone(data["next_action"]["task"])

    def test_escalation_records_interrupted_continuation(self):
        self.seed_v2("implementation")
        self.assertEqual(self._escalate().returncode, 0)
        esc = self.read_state()["escalation"]
        self.assertTrue(esc["required"])
        self.assertEqual(esc["previous_status"], "active")
        self.assertEqual(esc["interrupted_phase"], "implementation")
        self.assertEqual(esc["interrupted_action"]["role"], "ticket-executor")

    # -- routine command rejection -------------------------------------------

    def test_routine_advance_rejected_while_escalated(self):
        self.seed_v2("evidence_collection")
        self.assertEqual(self._escalate().returncode, 0)
        before = self.state_bytes()
        proc = self.cli("advance", self.TICKET, "--to", "evidence_audit")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("escalation", proc.stderr.lower())
        self.assertEqual(self.state_bytes(), before)

    def test_set_status_active_bypass_rejected(self):
        self.seed_v2("implementation")
        self.assertEqual(self._escalate().returncode, 0)
        before = self.state_bytes()
        proc = self.cli("set-status", self.TICKET, "--status", "active")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("escalation", proc.stderr.lower())
        self.assertEqual(self.state_bytes(), before)

    def test_set_status_escalation_required_still_allowed(self):
        self.seed_v2("implementation")
        self.assertEqual(self._escalate().returncode, 0)
        proc = self.cli("set-status", self.TICKET, "--status",
                        "escalation_required")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    # -- repeated escalation / restoration -----------------------------------

    def test_repeated_escalation_keeps_original_continuation(self):
        self.seed_v2("implementation")
        self.assertEqual(self._escalate("machine", "first").returncode, 0)
        first = self.read_state()["escalation"]
        self.assertEqual(first["previous_status"], "active")
        self.assertEqual(first["interrupted_phase"], "implementation")
        original_action = first["interrupted_action"]

        self.assertEqual(self._escalate("human", "second").returncode, 0)
        esc = self.read_state()["escalation"]
        self.assertTrue(esc["required"])
        self.assertEqual(esc["scope"], "human")
        self.assertEqual(esc["reason"], "second")
        self.assertEqual(esc["previous_status"], "active")
        self.assertEqual(esc["interrupted_phase"], "implementation")
        self.assertEqual(esc["interrupted_action"], original_action)

    def test_pause_and_block_restored_after_clear(self):
        for status in ("paused", "blocked"):
            with self.subTest(status=status):
                self._seed_implementation()
                self.assertEqual(self.cli("set-status", self.TICKET,
                                          "--status", status).returncode, 0)
                self.assertEqual(self._escalate().returncode, 0)
                esc = self.read_state()["escalation"]
                self.assertEqual(esc["previous_status"], status)
                proc = self._clear()
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                data = self.read_state()
                self.assertEqual(data["status"], status)
                self.assertFalse(data["escalation"]["required"])

    def test_machine_clear_recomputes_phase_action(self):
        self._seed_implementation(2)
        self.assertEqual(self._escalate().returncode, 0)
        proc = self._clear()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = self.read_state()
        self.assertEqual(data["status"], "active")
        self.assertEqual(data["next_action"]["role"], "ticket-executor")
        self.assertEqual(data["next_action"]["task"], 1)

    # -- ordinary senior recovery (HARDEN-003 Task 1) -------------------------

    def test_ordinary_recovery_can_reaudit_and_register(self):
        """An unresolved escalation lets the senior re-audit and re-register.

        The ordinary-phase deadlock: while escalated in `implementation`, the
        senior edits the Evidence, re-audits it, re-binds the gate, registers
        a corrected bounded Plan and records the decision, then clears with a
        referenced resolution into the retained phase.
        """
        self._seed_implementation(2)
        self.assertEqual(self._escalate("machine", "plan deviation").returncode,
                         0)

        # Re-audit outside evidence_audit: fresh round bound to fresh bytes.
        self.write_evidence(round_no=2)
        self.write_audit(gate="sufficient", round_no=2)
        audit_proc = self.cli("set-gate", self.TICKET, "--gate", "sufficient",
                              "--round", "2")

        # A corrected, bounded Plan registered in the retained phase.
        rel = self.write_plan(3, name="recovery-plan.md")
        register_proc = self.cli("register-plan", self.TICKET, "--path", rel,
                                 "--total", "3")

        clear_proc = self._clear("resolved per recovery-plan.md and decision.md")

        self.assertEqual(audit_proc.returncode, 0,
                         audit_proc.stdout + audit_proc.stderr)
        self.assertEqual(register_proc.returncode, 0,
                         register_proc.stdout + register_proc.stderr)
        self.assertEqual(clear_proc.returncode, 0,
                         clear_proc.stdout + clear_proc.stderr)
        data = self.read_state()
        self.assertFalse(data["escalation"]["required"])
        self.assertEqual(data["phase"], "implementation")
        self.assertEqual(data["evidence"]["round"], 2)
        self.assertEqual(data["implementation"]["total_tasks"], 3)
        self.assertEqual(data["next_action"]["role"], "ticket-executor")
        self.assertEqual(data["next_action"]["task"], 1)

    def test_clear_rejects_incoherent_retained_phase(self):
        """Every incoherence blocks the clear and leaves State bytes unchanged."""
        # missing Decision artifact
        self._escalated_implementation(1)
        os.remove(os.path.join(self.work, "decision.md"))
        before = self.state_bytes()
        proc = self._clear()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

        # stale gate: the audited Evidence changed after the verdict
        self._escalated_implementation(1)
        with open(os.path.join(self.work, "evidence.md"), "a",
                  encoding="utf-8") as fh:
            fh.write("\n<!-- late edit -->\n")
        before = self.state_bytes()
        proc = self._clear()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

        # stale Plan: the registered Plan drifted after registration
        self._escalated_implementation(1)
        rel = self.read_state()["source_artifacts"]["plan"]["path"]
        with open(os.path.join(self.root, rel), "a", encoding="utf-8") as fh:
            fh.write("\n<!-- drifted byte -->\n")
        before = self.state_bytes()
        proc = self._clear()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

        # stale recorded Review: the reviewed code moved after the verdict
        self._reset_recovery_residue()
        reviewed = self.prepare_v2_review(total=1)
        self.write_review("pass", reviewed_commit=reviewed)
        self.assertEqual(self.cli("set-review", self.TICKET, "--verdict",
                                  "pass").returncode, 0)
        self.assertEqual(self._escalate().returncode, 0)
        self.commit_code("src/late.py", "def late():\n    return 3\n")
        before = self.state_bytes()
        proc = self._clear()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

        # incoherent counters
        self._escalated_implementation(2)
        data = self.read_state()
        data["implementation"]["current_task"] = 2
        self.write_state(data)
        before = self.state_bytes()
        proc = self._clear()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

        # unconfirmed adoption checkpoint
        self._escalated_implementation(1)
        data = self.read_state()
        data["migration"] = {"adopted_existing_repo": True}
        data["adoption_checkpoint"] = {
            "repository_understood": True,
            "active_ticket_identified": True,
            "current_phase_identified": True,
            "remaining_work_identified": True,
            "critical_invariants_identified": True,
            "continuation_safe": False,
        }
        self.write_state(data)
        before = self.state_bytes()
        proc = self._clear()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

        # invalid resolution: no supporting reference
        self._escalated_implementation(1)
        before = self.state_bytes()
        proc = self._clear("all good now")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_clear_pending_review(self):
        """A pending Review clears only with every original task complete."""
        self.prepare_v2_review(total=2)
        # A pending Review with unfinished original tasks must not clear.
        data = self.read_state()
        data["implementation"]["current_task"] = 1
        data["implementation"]["completed_tasks"] = [1]
        self.write_state(data)
        self.assertEqual(self._escalate().returncode, 0)
        before = self.state_bytes()
        clear_proc = self._clear()
        self.assertEqual(clear_proc.returncode, 1,
                         clear_proc.stdout + clear_proc.stderr)
        self.assertEqual(self.state_bytes(), before)

        # With every original task complete, the same escalation clears and
        # the pending review continues normally in the retained phase.
        data = self.read_state()
        data["implementation"]["current_task"] = 2
        data["implementation"]["completed_tasks"] = [1, 2]
        self.write_state(data)
        clear_proc = self._clear()
        self.assertEqual(clear_proc.returncode, 0,
                         clear_proc.stdout + clear_proc.stderr)
        data = self.read_state()
        self.assertFalse(data["escalation"]["required"])
        self.assertEqual(data["phase"], "review")
        self.assertEqual(data["status"], "active")
        self.assertEqual(data["next_action"]["role"], "reviewer")

    def test_clear_failed_review_with_appended_repair(self):
        """A valid appended rework clears into the normal repair path."""
        reviewed = self.prepare_v2_review(total=1)
        self.write_review("changes_requested", reviewed_commit=reviewed)
        self.assertEqual(self.cli("set-review", self.TICKET, "--verdict",
                                  "changes_requested").returncode, 0)
        rel = self.write_plan(2)  # strictly appended, not-yet-executed rework
        self.assertEqual(self.cli("register-plan", self.TICKET, "--path", rel,
                                  "--total", "2").returncode, 0)

        self.assertEqual(self._escalate().returncode, 0)
        clear_proc = self._clear()
        self.assertEqual(clear_proc.returncode, 0,
                         clear_proc.stdout + clear_proc.stderr)
        data = self.read_state()
        self.assertFalse(data["escalation"]["required"])
        self.assertEqual(data["phase"], "review")
        self.assertEqual(data["review"]["verdict"], "changes_requested")

        # The ordinary repair path then executes: review -> implementation.
        repair_proc = self.cli("advance", self.TICKET, "--to", "implementation")
        self.assertEqual(repair_proc.returncode, 0,
                         repair_proc.stdout + repair_proc.stderr)
        data = self.read_state()
        self.assertEqual(data["implementation"]["current_task"], 1)
        self.assertEqual(data["review"]["verdict"], "pending")
        self.assertEqual(data["next_action"]["task"], 2)

    def test_recovery_preserves_status_and_prefix(self):
        """Paused/blocked recovery keeps the Status; the completed prefix binds once."""
        for previous in ("paused", "blocked"):
            with self.subTest(status=previous):
                self._seed_implementation(2)
                self.assertEqual(self.cli("set-status", self.TICKET,
                                          "--status", previous).returncode, 0)
                self.assertEqual(self._escalate().returncode, 0)
                clear_proc = self._clear()
                self.assertEqual(clear_proc.returncode, 0,
                                 clear_proc.stdout + clear_proc.stderr)
                data = self.read_state()
                self.assertEqual(data["status"], previous)
                self.assertFalse(data["escalation"]["required"])
                self.assertEqual(data["phase"], "implementation")

                # The restored Status is not silently executable, and the
                # cleared escalation grants no further out-of-phase writes.
                before = self.state_bytes()
                proc = self.cli("complete-task", self.TICKET)
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertEqual(self.state_bytes(), before)
                rel = self.write_plan(1, name="after-clear.md")
                proc = self.cli("register-plan", self.TICKET, "--path", rel,
                                "--total", "1")
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertEqual(self.state_bytes(), before)

        # An absent historical completed prefix binds once: the first
        # reconstruction registration records it, and a later registration
        # must match the recorded contracts even while the reconstruction is
        # still active.
        self.seed_v1("implementation")
        data = self.read_state()
        data["implementation"] = {"current_task": 1, "total_tasks": 2,
                                  "completed_tasks": [1]}
        self.write_state(data)
        self.assertEqual(self.cli("upgrade-ticket", self.TICKET).returncode, 0)
        rel = self.write_plan(2)
        self.assertEqual(self.cli("register-plan", self.TICKET, "--path", rel,
                                  "--total", "2").returncode, 0)
        # A repeated registration that preserves the prefix stays allowed.
        self.assertEqual(self.cli("register-plan", self.TICKET, "--path", rel,
                                  "--total", "2").returncode, 0)
        # Rewriting the completed contract is rejected, bytes unchanged.
        rewritten = valid_plan(self.TICKET, 2).replace(
            "Carry out bounded step 1 for the fixture.",
            "REDESIGNED: do something else entirely.")
        with open(os.path.join(self.root, rel), "w", encoding="utf-8",
                  newline="") as fh:
            fh.write(rewritten)
        before = self.state_bytes()
        proc = self.cli("register-plan", self.TICKET, "--path", rel,
                        "--total", "2")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    # -- resolution requirement (machine + human) ----------------------------

    def test_clear_without_resolution_rejected(self):
        self.seed_v2("implementation")
        self.assertEqual(self._escalate().returncode, 0)
        before = self.state_bytes()
        proc = self.cli("escalate", self.TICKET, "--clear")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("resolution", proc.stderr.lower())
        self.assertEqual(self.state_bytes(), before)

    def test_blank_resolution_rejected(self):
        self.seed_v2("implementation")
        self.assertEqual(self._escalate().returncode, 0)
        before = self.state_bytes()
        proc = self.cli("escalate", self.TICKET, "--clear",
                        "--resolution", "   ")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_resolution_without_reference_rejected(self):
        self.seed_v2("implementation")
        self.assertEqual(self._escalate().returncode, 0)
        before = self.state_bytes()
        proc = self._clear("all good now")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_human_clear_requires_user_answer_reference(self):
        self.seed_v2("implementation")
        self.assertEqual(self._escalate("human", "need the user").returncode, 0)
        before = self.state_bytes()
        proc = self._clear("resolved per decision.md and F-01")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("user", proc.stderr.lower())
        self.assertEqual(self.state_bytes(), before)

    def test_valid_human_resolution_clears(self):
        self._seed_implementation()
        self.assertEqual(self._escalate("human", "need the user").returncode, 0)
        proc = self._clear("user chose option B per decision.md and F-01")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = self.read_state()
        self.assertFalse(data["escalation"]["required"])
        self.assertEqual(data["status"], "active")
        self.assertIn("user chose", data["escalation"]["resolution"])

    # -- completion / advance rejected only by escalation --------------------

    def test_registered_implementation_blocked_by_escalation(self):
        self._seed_implementation(1)
        self.assertEqual(self._escalate().returncode, 0)
        before = self.state_bytes()
        proc = self.cli("complete-task", self.TICKET)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("escalation", proc.stderr.lower())
        self.assertEqual(self.state_bytes(), before)

        # Clearing restores a valid action; completion then proceeds normally.
        self.assertEqual(self._clear().returncode, 0)
        self.assertEqual(self.read_state()["status"], "active")
        self.assertEqual(self.cli("complete-task", self.TICKET).returncode, 0)

    # -- validate divergence -------------------------------------------------

    def test_route_corruption_reported_by_validate(self):
        self.seed_v2("implementation")
        self.assertEqual(self._escalate().returncode, 0)
        data = self.read_state()
        data["next_action"]["role"] = "ticket-executor"
        self.write_state(data)
        proc = self.cli("validate", self.TICKET)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("next_action.role", proc.stdout)

    def test_status_divergence_reported_by_validate(self):
        self.seed_v2("implementation")
        self.assertEqual(self._escalate().returncode, 0)
        data = self.read_state()
        data["status"] = "active"
        self.write_state(data)
        proc = self.cli("validate", self.TICKET)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("escalation.required", proc.stdout)

    # -- nothing to interrupt -------------------------------------------------

    def test_escalating_done_ticket_rejected(self):
        self.seed_v2("done")
        before = self.state_bytes()
        proc = self._escalate()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_escalating_abandoned_ticket_rejected(self):
        self.seed_v2("implementation")
        self.assertEqual(self.cli("set-status", self.TICKET, "--status",
                                  "abandoned").returncode, 0)
        before = self.state_bytes()
        proc = self._escalate()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    # -- v1 compatibility ----------------------------------------------------

    def test_v1_escalate_and_clear_unchanged(self):
        # Explicit v1 ticket; seed_v2 is deliberately not called. setUp's `start`
        # no longer leaves v1 now that the bundled default is v2 (Task 2).
        self.seed_v1("requirement")
        proc = self.cli("escalate", self.TICKET, "--scope", "human",
                        "--reason", "blocked on decision")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = self.read_state()
        self.assertEqual(data.get("workflow_version", 1), 1)
        self.assertTrue(data["escalation"]["required"])
        self.assertEqual(data["escalation"]["scope"], "human")
        self.assertEqual(data["status"], "active")

        proc = self.cli("escalate", self.TICKET, "--clear")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = self.read_state()
        self.assertFalse(data["escalation"]["required"])
        self.assertEqual(data["escalation"]["scope"], "machine")
        self.assertEqual(data["status"], "active")


if __name__ == "__main__":
    unittest.main()
