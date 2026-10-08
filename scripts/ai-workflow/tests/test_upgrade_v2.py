"""Explicit v1->v2 Ticket conversion and protocol upgrade (SCOUT-007 Task 1).

Covers: `upgrade` rewrites only the protocol and never a Ticket State (its
second return value is `[]`); `upgrade-ticket` explicitly converts one
interpretable active v1 Ticket — keeping phase/history, recording the gate
reset/review-pending/reconstruction facts and the senior-resolution escalation —
while a historic `done` v1 Ticket, an uninterpretable version, or a malformed
state is rejected unchanged, and an already-v2 Ticket is a byte-preserving
no-op. The reconstruction is then cleared only once the retained phase's current
contracts are supplied through the public commands; conversion itself fabricates
no audit, Plan, or review pass. Every rejection asserts State bytes unchanged.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import start            # noqa: E402
import state            # noqa: E402
import upgrade          # noqa: E402
from v2_support import V2CLITestCase  # noqa: E402

RESOLUTION = "reconstructed per decision.md and F-01"


def _kit_workflow_dir():
    # this file: scripts/ai-workflow/tests/test_upgrade_v2.py -> 4 levels up.
    kit = os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return os.path.join(kit, ".ai", "workflow")


def _read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


class ProtocolUpgradePreservesTicketsTest(unittest.TestCase):
    """`upgrade` rewrites only the protocol; Ticket State is never touched."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        # Install the bundled protocol, then pin the installed copy one version
        # older so the upgrade has work to do. The bundled default is never
        # assumed to be v1 (Task 2 flips it).
        shutil.copytree(_kit_workflow_dir(),
                        os.path.join(self.root, ".ai", "workflow"))
        tmpl = os.path.join(self.root, ".ai", "workflow",
                            "templates", "state.yaml")
        data = state.load_file(tmpl)
        data["workflow_version"] = (upgrade.kit_workflow_version() or 1) - 1
        state.save_file(tmpl, data)

    def tearDown(self):
        self._tmp.cleanup()

    def _seed(self, ticket_id, phase):
        start.start(self.root, ticket_id, title="ticket " + ticket_id)
        path = os.path.join(self.root, ".ai", "work", ticket_id, "state.yaml")
        data = state.load_file(path)
        data["workflow_version"] = 1
        data["phase"] = phase
        state.save_file(path, data)
        return path

    def test_protocol_upgrade_preserves_ticket_bytes(self):
        active = self._seed("T-active", "implementation")
        done = self._seed("T-done", "done")
        before_active = _read_bytes(active)
        before_done = _read_bytes(done)

        updated, bumped = upgrade.upgrade(self.root)

        self.assertTrue(updated)          # the older protocol was overwritten
        self.assertEqual(bumped, [])      # ... but no Ticket was promoted
        self.assertEqual(_read_bytes(active), before_active)
        self.assertEqual(_read_bytes(done), before_done)
        self.assertEqual(state.load_file(active)["workflow_version"], 1)
        self.assertEqual(state.load_file(done)["phase"], "done")

        # The protocol upgrade brings the installed template up to the kit's
        # shipped default, which Task 2 flips to workflow_version 2.
        tmpl = os.path.join(self.root, ".ai", "workflow", "templates",
                            "state.yaml")
        self.assertEqual(upgrade.kit_workflow_version(), 2)
        self.assertEqual(state.load_file(tmpl)["workflow_version"], 2)
        self.assertEqual(upgrade.installed_workflow_version(self.root), 2)


class UpgradeTicketV2Test(V2CLITestCase):

    def _upgrade_ticket(self):
        return self.cli("upgrade-ticket", self.TICKET)

    def _clear(self, resolution=RESOLUTION):
        return self.cli("escalate", self.TICKET, "--clear",
                        "--resolution", resolution)

    def _half_completed(self, phase="implementation"):
        """v1 ticket with ordered half-completed history and an unknown map."""
        self.seed_v1(phase)
        data = self.read_state()
        data["implementation"] = {
            "current_task": 1, "total_tasks": 2, "completed_tasks": [1],
        }
        data["unknown_map"] = {"kept": [1, 2], "note": "preserve me"}
        self.write_state(data)
        return data

    # -- step 1: explicit conversion preserves history -----------------------

    def test_explicit_upgrade_keeps_half_completed_history(self):
        original = self._half_completed("implementation")
        before_action = original["next_action"]

        proc = self._upgrade_ticket()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        out = self.read_state()
        self.assertEqual(out["workflow_version"], 2)
        self.assertEqual(out["phase"], "implementation")
        self.assertEqual(out["implementation"], original["implementation"])
        self.assertEqual(out["source_artifacts"], original["source_artifacts"])
        self.assertEqual(out["unknown_map"], original["unknown_map"])
        self.assertEqual(out["evidence"]["gate"], "insufficient")
        self.assertEqual(out["review"]["verdict"], "pending")
        self.assertTrue(out["upgrade"]["requires_reconstruction"])
        self.assertEqual(out["upgrade"]["from_version"], 1)
        self.assertEqual(out["upgrade"]["previous_gate"], "insufficient")
        self.assertEqual(out["next_action"]["role"], "workflow-bootstrap")
        self.assertEqual(out["status"], "escalation_required")
        esc = out["escalation"]
        self.assertTrue(esc["required"])
        self.assertEqual(esc["scope"], "machine")
        self.assertEqual(esc["interrupted_phase"], "implementation")
        self.assertEqual(esc["interrupted_action"],
                         {"role": before_action["role"],
                          "action": before_action["action"],
                          "task": before_action["task"]})

        # Conversion creates no past audit, registered Plan, or review pass.
        self.assertNotIn("report_sha256", out["evidence"])
        self.assertNotIn("audit_sha256", out["evidence"])
        self.assertIsNone(
            (out["source_artifacts"].get("plan") or {}).get("sha256"))

        # Repeated conversion is a byte-preserving no-op.
        after = self.state_bytes()
        proc = self._upgrade_ticket()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), after)

    def test_already_v2_conversion_is_a_byte_preserving_noop(self):
        self.seed_v2("planning")
        before = self.state_bytes()
        proc = self._upgrade_ticket()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_historical_done_stays_v1(self):
        self.seed_v1("done")
        before = self.state_bytes()
        proc = self._upgrade_ticket()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(self.state_bytes(), before)
        self.assertEqual(self.read_state()["workflow_version"], 1)

    def test_uninterpretable_versions_rejected_unchanged(self):
        for bad in (0, 3, True):
            with self.subTest(version=bad):
                self.seed_v1("implementation")
                data = self.read_state()
                data["workflow_version"] = bad
                self.write_state(data)
                before = self.state_bytes()
                proc = self._upgrade_ticket()
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)
                self.assertEqual(self.state_bytes(), before)

    def test_malformed_state_rejected_unchanged(self):
        path = self._state_path()
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write("phase: &anchor not-in-subset\n")
        before = _read_bytes(path)
        proc = self._upgrade_ticket()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(_read_bytes(path), before)

    def test_missing_argument_is_usage_error(self):
        proc = self.cli("upgrade-ticket")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)

    def test_unknown_ticket_rejected(self):
        proc = self.cli("upgrade-ticket", "NOPE")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)

    def test_conversion_preserves_paused_and_blocked_status(self):
        for status in ("paused", "blocked"):
            with self.subTest(status=status):
                self.seed_v1("evidence_collection")
                proc = self.cli("set-status", self.TICKET, "--status", status)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                proc = self._upgrade_ticket()
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                out = self.read_state()
                self.assertEqual(out["status"], "escalation_required")
                self.assertEqual(out["escalation"]["previous_status"], status)

                # Clearing restores the interrupted Status, which is never
                # silently promoted to active (so it is not auto-executable).
                proc = self._clear()
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                cleared = self.read_state()
                self.assertEqual(cleared["status"], status)
                self.assertFalse(cleared["escalation"]["required"])
                self.assertFalse(cleared["upgrade"]["requires_reconstruction"])

    def test_escalated_or_abandoned_status_rejected_unchanged(self):
        for status in ("escalation_required", "abandoned"):
            with self.subTest(status=status):
                self.seed_v1("implementation")
                data = self.read_state()
                data["status"] = status
                self.write_state(data)
                before = self.state_bytes()
                proc = self._upgrade_ticket()
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)
                self.assertIn(status, proc.stderr)
                self.assertEqual(self.state_bytes(), before)
                self.assertEqual(self.read_state()["workflow_version"], 1)

    # -- step 4: retained-phase reconstruction -------------------------------

    def test_reconstruct_implementation_without_fake_history(self):
        self._half_completed("implementation")
        self.assertEqual(self._upgrade_ticket().returncode, 0)

        # The senior resolver supplies the current contracts through the public
        # commands: a current sufficient gate and a two-task Plan whose completed
        # prefix is the retained work.
        self.write_evidence(round_no=1)
        self.write_audit(gate="sufficient", round_no=1)
        proc = self.cli("set-gate", self.TICKET, "--gate", "sufficient",
                        "--round", "1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.write_decision()
        rel = self.write_plan(2)
        proc = self.cli("register-plan", self.TICKET, "--path", rel,
                        "--total", "2")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        # Registering records the completed hashes without touching the numeric
        # history.
        mid = self.read_state()
        self.assertEqual(mid["implementation"]["current_task"], 1)
        self.assertEqual(mid["implementation"]["completed_tasks"], [1])
        self.assertEqual(len(mid["implementation"]["task_hashes"]), 2)

        proc = self._clear()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        cleared = self.read_state()
        self.assertEqual(cleared["phase"], "implementation")
        self.assertEqual(cleared["status"], "active")
        self.assertFalse(cleared["escalation"]["required"])
        self.assertFalse(cleared["upgrade"]["requires_reconstruction"])
        self.assertEqual(cleared["implementation"]["current_task"], 1)
        self.assertEqual(cleared["next_action"]["role"], "ticket-executor")
        self.assertEqual(cleared["next_action"]["task"], 2)

    def test_reconstruct_review_can_resume_pending_review(self):
        self.seed_v1("review")
        data = self.read_state()
        data["implementation"] = {
            "current_task": 2, "total_tasks": 2, "completed_tasks": [1, 2],
        }
        self.write_state(data)
        self.assertEqual(self._upgrade_ticket().returncode, 0)

        # A coherent completed Plan and current audit.
        self.write_evidence(round_no=1)
        self.write_audit(gate="sufficient", round_no=1)
        self.assertEqual(self.cli("set-gate", self.TICKET, "--gate", "sufficient",
                                  "--round", "1").returncode, 0)
        self.write_decision()
        rel = self.write_plan(2)
        self.assertEqual(self.cli("register-plan", self.TICKET, "--path", rel,
                                  "--total", "2").returncode, 0)

        proc = self._clear()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        cleared = self.read_state()
        self.assertEqual(cleared["phase"], "review")
        self.assertEqual(cleared["status"], "active")
        self.assertEqual(cleared["next_action"]["role"], "reviewer")
        self.assertEqual(cleared["review"]["verdict"], "pending")

        # A current pass is then recorded normally (no review was fabricated).
        reviewed = self.commit_all("fixture: reconstructed review tree")
        self.write_review("pass", reviewed_commit=reviewed)
        proc = self.cli("set-review", self.TICKET, "--verdict", "pass")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.read_state()["review"]["verdict"], "pass")

    def test_plain_v2_review_still_records_a_pass(self):
        # The upgrade changes must not disturb a normal (non-reconstructed) v2
        # Review lifecycle.
        reviewed = self.prepare_v2_review(total=1)
        self.write_review("pass", reviewed_commit=reviewed)
        proc = self.cli("set-review", self.TICKET, "--verdict", "pass")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_missing_contracts_reject_clear_unchanged(self):
        self._half_completed("implementation")
        self.assertEqual(self._upgrade_ticket().returncode, 0)
        # No current Evidence/audit/decision/Plan yet: clearing must not quietly
        # reconstruct, and must leave State bytes unchanged.
        before = self.state_bytes()
        proc = self._clear()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_unconfirmed_adoption_rejects_clear_unchanged(self):
        self.seed_v1("implementation")
        data = self.read_state()
        data["implementation"] = {
            "current_task": 1, "total_tasks": 2, "completed_tasks": [1],
        }
        data["migration"] = {"adopted_existing_repo": True}
        data["adoption_checkpoint"] = {
            "repository_understood": False,
            "active_ticket_identified": True,
            "current_phase_identified": True,
            "remaining_work_identified": True,
            "critical_invariants_identified": True,
            "continuation_safe": False,
        }
        self.write_state(data)
        self.assertEqual(self._upgrade_ticket().returncode, 0)

        self.write_evidence(round_no=1)
        self.write_audit(gate="sufficient", round_no=1)
        self.assertEqual(self.cli("set-gate", self.TICKET, "--gate", "sufficient",
                                  "--round", "1").returncode, 0)
        self.write_decision()
        rel = self.write_plan(2)
        self.assertEqual(self.cli("register-plan", self.TICKET, "--path", rel,
                                  "--total", "2").returncode, 0)

        before = self.state_bytes()
        proc = self._clear()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_cleared_reconstruction_grants_no_out_of_phase_writes(self):
        """After the clear, the stale recovery flags grant no further writes."""
        original = self._half_completed("implementation")
        self.assertEqual(self._upgrade_ticket().returncode, 0)

        # The reconstruction context permits the senior's out-of-phase writes.
        self.write_evidence(round_no=1)
        self.write_audit(gate="sufficient", round_no=1)
        self.assertEqual(self.cli("set-gate", self.TICKET, "--gate", "sufficient",
                                  "--round", "1").returncode, 0)
        self.write_decision()
        rel = self.write_plan(2)
        self.assertEqual(self.cli("register-plan", self.TICKET, "--path", rel,
                                  "--total", "2").returncode, 0)
        self.assertEqual(self._clear().returncode, 0)

        # Unknown extension fields survive the atomic clear untouched.
        self.assertEqual(self.read_state()["unknown_map"],
                         original["unknown_map"])

        # Reconstruction is over: the cleared flag no longer permits
        # out-of-phase set-gate or register-plan, and State bytes stay put.
        before = self.state_bytes()
        proc = self.cli("set-gate", self.TICKET, "--gate", "insufficient")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)
        proc = self.cli("register-plan", self.TICKET, "--path", rel,
                        "--total", "2")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)


if __name__ == "__main__":
    unittest.main()