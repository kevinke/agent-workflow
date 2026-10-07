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

from v2_support import V2CLITestCase  # noqa: E402

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
        """Reach a genuinely execution-ready v2 implementation."""
        self._seed_planning()
        rel = self.write_plan(total)
        proc = self.cli("register-plan", self.TICKET, "--path", rel,
                        "--total", str(total))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = self.cli("advance", self.TICKET, "--to", "implementation")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

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
                self.seed_v2("implementation")
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
        self.seed_v2("implementation")
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
