"""Release defaults and the full installed-target v2 lifecycle (SCOUT-007 T2).

Two concerns:

1. **Shipped defaults and compatibility.** `init`/`start` produce a v2 Ticket
   (`workflow_version: 2`, pending bindings, `review.verdict: pending`) whose
   requirement phase validates clean with incomplete scaffolds and no passing
   gate; an *unupgraded* v1 install keeps producing v1 work (Ruling C); repeat
   init/start are idempotent and never touch user content; the Reviewer role
   installs; source references are recorded by reference; a later-phase v2 start
   routes to senior reconstruction, never executor readiness; and a dirty adopt
   yields v2 with all six `adoption_checkpoint` booleans false, blocking execution
   until a senior confirms them.

2. **One complete installed-target CLI lifecycle** (`init` -> install roles ->
   `start` -> Scout report -> insufficient audit/follow-up -> sufficient audit ->
   decision/Plan -> escalate/resolve -> execution -> changes_requested/appended
   repair -> fresh pass -> `resume` -> done), asserting `validate` is clean at the
   eligible boundaries, the task history persists across the repair, and the
   final `pass` is recorded.

Everything is driven through the real CLI (`self.cli`).
"""

import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import state           # noqa: E402
import workflow_v2     # noqa: E402
from v2_support import (V2CLITestCase, install_v1_templates,  # noqa: E402
                        valid_audit, valid_evidence, valid_handoff,
                        valid_plan)

ADOPTION_CONFIRMATIONS = workflow_v2.ADOPTION_CONFIRMATIONS


class ReleaseDefaultsTest(V2CLITestCase):
    """The shipped default is v2; unupgraded v1 installs keep producing v1."""

    def _read_state_for(self, ticket):
        return state.load_file(
            os.path.join(self.root, ".ai", "work", ticket, "state.yaml"))

    def _write_for(self, ticket, name, text):
        full = os.path.join(self.root, ".ai", "work", ticket, name)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return full

    def _evidence_for(self, ticket, round_no):
        head = self._git("rev-parse", "HEAD").stdout.strip()
        return self._write_for(ticket, "evidence.md",
                               valid_evidence(ticket, round_no, head))

    def _audit_for(self, ticket, gate, round_no):
        with open(os.path.join(self.root, ".ai", "work", ticket,
                               "evidence.md"), "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
        return self._write_for(
            ticket, "evidence-audit.md",
            valid_audit(ticket, gate, round_no, digest))

    # -- defaults ------------------------------------------------------------

    def test_fresh_start_has_pending_v2_contracts(self):
        data = self.read_state()
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["workflow_version"], 2)
        self.assertEqual(data["phase"], "requirement")
        self.assertEqual(data["next_action"]["role"], "workflow-bootstrap")
        # Incomplete scaffolds, no crafted contracts, no passing gate.
        self.assertEqual(data["evidence"]["gate"], "insufficient")
        self.assertIsNone(data["evidence"]["report_sha256"])
        self.assertIsNone(data["evidence"]["audit_sha256"])
        self.assertEqual(data["implementation"]["task_hashes"], [])
        self.assertEqual(data["artifacts"]["review"], "review.md")
        self.assertEqual(data["review"]["verdict"], "pending")

        proc = self.cli("validate")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("no ERROR findings", proc.stdout)

    def test_old_installed_templates_keep_v1_starts(self):
        # An unupgraded v1 install must keep scaffolding v1 even though the kit
        # code ships a v2 default (Ruling C: resolve from the installed target).
        install_v1_templates(self.root)
        proc = self.cli("start", "T2", "--title", "legacy")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = self._read_state_for("T2")
        self.assertEqual(data["workflow_version"], 1)
        # The frozen v1 requirement route (checkpoint-handoff), not bootstrap.
        self.assertEqual(data["next_action"]["role"], "checkpoint-handoff")

    def test_repeat_init_and_start_preserve_user_content(self):
        user_path = os.path.join(self.work, "notes.md")
        with open(user_path, "w", encoding="utf-8", newline="") as fh:
            fh.write("user notes\n")
        before = self.capture_files()

        init_proc = self.cli("init")
        self.assertEqual(init_proc.returncode, 0,
                         init_proc.stdout + init_proc.stderr)
        self.assertIn("nothing to do", init_proc.stdout)
        start_proc = self.cli("start", self.TICKET)
        self.assertEqual(start_proc.returncode, 0,
                         start_proc.stdout + start_proc.stderr)
        self.assertIn("already started", start_proc.stdout)

        self.assertEqual(self.capture_files(), before)
        with open(user_path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "user notes\n")

    def test_install_skills_installs_reviewer(self):
        proc = self.cli("install-skills")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        reviewer = os.path.join(self.root, ".agents", "skills", "reviewer",
                                "SKILL.md")
        self.assertTrue(os.path.exists(reviewer), reviewer)

    def test_source_references_recorded_by_reference(self):
        proc = self.cli("start", "T2", "--spec", "docs/spec.md",
                        "--ticket", ".scratch/feature/01.md",
                        "--plan", "docs/plan.md")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = self._read_state_for("T2")
        self.assertEqual(data["source_artifacts"]["spec"]["path"],
                         "docs/spec.md")
        self.assertEqual(data["source_artifacts"]["ticket"]["path"],
                         ".scratch/feature/01.md")
        self.assertEqual(data["source_artifacts"]["plan"]["path"],
                         "docs/plan.md")
        # Recorded by reference only: nothing is copied into the repo.
        self.assertFalse(os.path.exists(os.path.join(self.root, "docs",
                                                     "spec.md")))
        self.assertFalse(os.path.exists(os.path.join(self.root, "docs",
                                                     "plan.md")))

    def test_start_invalid_phase_defaults_to_requirement(self):
        proc = self.cli("start", "T3", "--phase", "bogus")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self._read_state_for("T3")["phase"], "requirement")

    def test_unsupported_versions_rejected_without_state_write(self):
        for bad in (3, True):
            with self.subTest(version=bad):
                self.seed_v2("requirement")
                data = self.read_state()
                data["workflow_version"] = bad
                self.write_state(data)
                before = self.state_bytes()
                proc = self.cli("advance", self.TICKET, "--to",
                                "evidence_collection")
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)
                self.assertEqual(self.state_bytes(), before)

    def test_later_phase_v2_start_is_never_executor_ready(self):
        proc = self.cli("start", "T3", "--phase", "implementation")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = self._read_state_for("T3")
        self.assertEqual(data["workflow_version"], 2)
        self.assertEqual(data["phase"], "implementation")
        # Senior reconstruction, never a cheap executor's route.
        self.assertEqual(data["next_action"]["role"], "workflow-bootstrap")
        self.assertNotEqual(data["next_action"]["role"], "ticket-executor")

        # The scaffold surfaces readiness blockers (no registered Plan), not a
        # green light to execute.
        check = self.cli("validate", "T3")
        self.assertEqual(check.returncode, 1, check.stdout + check.stderr)
        self.assertIn("ERRORS PRESENT", check.stdout)

    # -- dirty adoption ------------------------------------------------------

    def test_dirty_adopt_needs_checkpoint_before_any_task_completes(self):
        proc = self.cli("adopt", "T2")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        adopted = self._read_state_for("T2")
        self.assertEqual(adopted["workflow_version"], 2)
        self.assertTrue(adopted["migration"]["adopted_existing_repo"])
        self.assertEqual(adopted["next_action"]["role"], "workflow-bootstrap")
        for name in ADOPTION_CONFIRMATIONS:
            self.assertIs(adopted["adoption_checkpoint"][name], False, name)

        # Drive T2 to a registered-Plan planning state through the real CLI.
        self.assertEqual(self.cli("advance", "T2", "--to",
                                  "evidence_collection").returncode, 0)
        self._evidence_for("T2", 1)
        self.assertEqual(self.cli("advance", "T2", "--to",
                                  "evidence_audit").returncode, 0)
        self._audit_for("T2", "sufficient", 1)
        self.assertEqual(self.cli("set-gate", "T2", "--gate", "sufficient",
                                  "--round", "1").returncode, 0)
        self.assertEqual(self.cli("advance", "T2", "--to",
                                  "technical_decision").returncode, 0)
        self._write_for("T2", "decision.md", "# Decision - T2\n")
        self.assertEqual(self.cli("advance", "T2", "--to",
                                  "planning").returncode, 0)
        plan_rel = os.path.join(".ai", "work", "T2", "plan.md")
        self._write_for("T2", "plan.md", valid_plan("T2", 1))
        self.assertEqual(self.cli("register-plan", "T2", "--path", plan_rel,
                                  "--total", "1").returncode, 0)

        # Entering implementation is blocked: continuation_safe is false and the
        # other prerequisites are not all confirmed.
        before = self._read_state_for("T2")
        blocked = self.cli("advance", "T2", "--to", "implementation")
        self.assertEqual(blocked.returncode, 1, blocked.stdout + blocked.stderr)
        self.assertIn("adoption checkpoint", blocked.stderr)
        self.assertEqual(self._read_state_for("T2"), before)

        # `complete-task` is likewise rejected before the checkpoint is confirmed
        # (seed an implementation-shaped State; the command guard is what is
        # under test here).
        data = self._read_state_for("T2")
        data["phase"] = "implementation"
        data["next_action"] = {"role": "ticket-executor",
                               "action": "implement current task", "task": 1}
        state.save_file(os.path.join(self.root, ".ai", "work", "T2",
                                     "state.yaml"), data)
        before = self._read_state_for("T2")
        rejected = self.cli("complete-task", "T2", "--total", "1")
        self.assertEqual(rejected.returncode, 1,
                         rejected.stdout + rejected.stderr)
        self.assertIn("adoption checkpoint", rejected.stderr)
        self.assertEqual(self._read_state_for("T2"), before)

        # A senior confirms all six booleans; only then may a task complete.
        data = self._read_state_for("T2")
        data["adoption_checkpoint"] = {name: True
                                       for name in ADOPTION_CONFIRMATIONS}
        state.save_file(os.path.join(self.root, ".ai", "work", "T2",
                                     "state.yaml"), data)
        done = self.cli("complete-task", "T2", "--total", "1")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self._read_state_for("T2")["implementation"]
                         ["current_task"], 1)


class InstalledLifecycleV2Test(V2CLITestCase):
    """One complete installed-target CLI lifecycle with follow-up and rework."""

    def _assert_validate_ok(self, boundary):
        proc = self.cli("validate")
        self.assertEqual(proc.returncode, 0,
                         "%s: %s" % (boundary, proc.stdout + proc.stderr))
        self.assertIn("no ERROR findings", proc.stdout)

    def test_installed_lifecycle_with_followup_and_rework(self):
        # -- install roles --------------------------------------------------
        roles = self.cli("install-skills")
        self.assertEqual(roles.returncode, 0, roles.stdout + roles.stderr)
        self.assertTrue(os.path.exists(
            os.path.join(self.root, ".agents", "skills", "reviewer",
                         "SKILL.md")))

        # -- requirement (as scaffolded by `start`) -------------------------
        self.assertIsNone(self.read_state()["next_action"]["task"])
        self._assert_validate_ok("requirement")

        # -- Scout report at evidence_collection ----------------------------
        self.write_evidence(round_no=1)
        self.assertEqual(self.cli("advance", self.TICKET, "--to",
                                  "evidence_collection").returncode, 0)
        self._assert_validate_ok("evidence_collection")

        # -- insufficient audit -> follow-up ---------------------------------
        self.write_audit(gate="insufficient", round_no=1)
        self.assertEqual(self.cli("advance", self.TICKET, "--to",
                                  "evidence_audit").returncode, 0)
        self.assertEqual(self.cli("set-gate", self.TICKET, "--gate",
                                  "insufficient", "--round", "1").returncode, 0)
        self._assert_validate_ok("evidence_audit (insufficient)")
        self.assertEqual(self.cli("advance", self.TICKET, "--to",
                                  "followup_evidence").returncode, 0)
        self._assert_validate_ok("followup_evidence")

        # -- sufficient audit ------------------------------------------------
        self.write_evidence(round_no=2)
        self.assertEqual(self.cli("advance", self.TICKET, "--to",
                                  "evidence_audit").returncode, 0)
        self.write_audit(gate="sufficient", round_no=2)
        self.assertEqual(self.cli("set-gate", self.TICKET, "--gate",
                                  "sufficient", "--round", "2").returncode, 0)
        self._assert_validate_ok("evidence_audit (sufficient)")

        # -- decision and Plan ----------------------------------------------
        self.assertEqual(self.cli("advance", self.TICKET, "--to",
                                  "technical_decision").returncode, 0)
        self._assert_validate_ok("technical_decision")
        self.write_decision()
        self.assertEqual(self.cli("advance", self.TICKET, "--to",
                                  "planning").returncode, 0)
        rel = self.write_plan(2)
        self.assertEqual(self.cli("register-plan", self.TICKET, "--path", rel,
                                  "--total", "2").returncode, 0)
        self._assert_validate_ok("planning")

        # -- escalate / resolve ---------------------------------------------
        escalated = self.cli("escalate", self.TICKET, "--scope", "machine",
                             "--reason", "blocked on an open decision")
        self.assertEqual(escalated.returncode, 0, escalated.stdout
                         + escalated.stderr)
        blocked = self.cli("advance", self.TICKET, "--to", "implementation")
        self.assertEqual(blocked.returncode, 1, blocked.stdout + blocked.stderr)
        cleared = self.cli("escalate", self.TICKET, "--clear", "--resolution",
                           "resolved per F-01 recorded in decision.md")
        self.assertEqual(cleared.returncode, 0, cleared.stdout + cleared.stderr)
        self.assertFalse(self.read_state()["escalation"]["required"])

        # -- execution -------------------------------------------------------
        self.assertEqual(self.cli("advance", self.TICKET, "--to",
                                  "implementation").returncode, 0)
        for _ in range(2):
            proc = self.cli("complete-task", self.TICKET, "--total", "2")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self._assert_validate_ok("implementation")

        # -- changes_requested + appended repair -----------------------------
        # The review entry boundary needs a concrete handoff (HARDEN-007); the
        # file persists, so the later re-entry and done stay satisfied too.
        self.write_handoff()
        self.assertEqual(self.cli("advance", self.TICKET, "--to",
                                  "review").returncode, 0)
        reviewed = self.commit_all("fixture: reviewed tree")
        self.write_review("changes_requested", reviewed_commit=reviewed)
        proc = self.cli("set-review", self.TICKET, "--verdict",
                        "changes_requested")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self._assert_validate_ok("review (changes_requested)")

        # Append a rework task and return to implementation.
        repair_rel = self.write_plan(3)
        self.assertEqual(self.cli("register-plan", self.TICKET, "--path",
                                  repair_rel, "--total", "3").returncode, 0)
        proc = self.cli("advance", self.TICKET, "--to", "implementation")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.read_state()["review"]["verdict"], "pending")
        proc = self.cli("complete-task", self.TICKET, "--total", "3")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self._assert_validate_ok("implementation (repair)")

        # -- fresh pass ------------------------------------------------------
        self.assertEqual(self.cli("advance", self.TICKET, "--to",
                                  "review").returncode, 0)
        passed = self.commit_all("fixture: passed tree")
        self.write_review("pass", reviewed_commit=passed)
        proc = self.cli("set-review", self.TICKET, "--verdict", "pass")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        # Persisted task history survives the rework.
        impl = self.read_state()["implementation"]
        self.assertEqual(impl["current_task"], 3)
        self.assertEqual(impl["completed_tasks"], [1, 2, 3])
        self.assertEqual(impl["total_tasks"], 3)
        self.assertEqual(len(impl["task_hashes"]), 3)

        # -- resume and done -------------------------------------------------
        brief = self.cli("resume", self.TICKET)
        self.assertEqual(brief.returncode, 0, brief.stdout + brief.stderr)

        proc = self.cli("advance", self.TICKET, "--to", "done")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        final = self.read_state()
        self.assertEqual(final["phase"], "done")
        self.assertEqual(final["review"]["verdict"], "pass")
        self._assert_validate_ok("done")


class RecoveryKindBootstrapTest(unittest.TestCase):
    """Direct dict-level coverage of `recovery_kind`'s bootstrap branch.

    `recovery.kind: bootstrap` alone grants nothing: the kind is recognized
    only on a *coherent* unresolved v2 recovery (the escalation recorded and
    the Status locked to `escalation_required`), and a foreign kind falls
    through to the ordinary escalation reading (HARDEN-003 Task 1 predicate).
    """

    @staticmethod
    def _bootstrap_state():
        return {
            "workflow_version": 2,
            "status": "escalation_required",
            "escalation": {"required": True, "scope": "machine",
                           "reason": "late-phase bootstrap"},
            "recovery": {"kind": "bootstrap"},
        }

    def test_bootstrap_marker_with_coherent_escalation_is_bootstrap(self):
        self.assertEqual(workflow_v2.recovery_kind(self._bootstrap_state()),
                         "bootstrap")

    def test_divergent_facts_grant_no_bootstrap_recovery(self):
        diverged = self._bootstrap_state()
        diverged["status"] = "active"
        self.assertIsNone(workflow_v2.recovery_kind(diverged))

        unresolved = self._bootstrap_state()
        unresolved["escalation"]["required"] = False
        self.assertIsNone(workflow_v2.recovery_kind(unresolved))

        v1 = self._bootstrap_state()
        v1["workflow_version"] = 1
        self.assertIsNone(workflow_v2.recovery_kind(v1))

        # A foreign recovery kind is not a bootstrap: with the escalation
        # coherent it reads as the ordinary escalation recovery instead.
        foreign = self._bootstrap_state()
        foreign["recovery"] = {"kind": "other"}
        self.assertEqual(workflow_v2.recovery_kind(foreign), "escalation")


class LateBootstrapRecoveryTest(V2CLITestCase):
    """A v2 start/adopt directly at implementation/review is recoverable.

    The scaffold enters an explicit bootstrap recovery (`recovery.kind:
    bootstrap` + an unresolved machine escalation routed to the
    workflow-bootstrap senior resolver): resume names the resolver, completion
    is rejected, a premature clear is rejected, and only the public recovery
    sequence (audit -> register-plan -> Decision -> adoption checkpoint -> a
    referenced `escalate --clear`) reaches ordinary execution or pending
    review. The requested phase is retained and no `upgrade` conversion facts
    are invented for the freshly created v2 State (HARDEN-003 Task 2).
    """

    RESOLUTION = "reconstructed per evidence.md, decision.md and plan.md"

    # -- per-ticket helpers (the fixture's own helpers are T1-bound) ----------

    def _work(self, ticket):
        return os.path.join(self.root, ".ai", "work", ticket)

    def _state_of(self, ticket):
        return state.load_file(
            os.path.join(self._work(ticket), "state.yaml"))

    def _bytes_of(self, ticket):
        with open(os.path.join(self._work(ticket), "state.yaml"), "rb") as fh:
            return fh.read()

    def _write_for(self, ticket, name, text):
        full = os.path.join(self._work(ticket), name)
        with open(full, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return full

    def _late_ticket(self, command, phase):
        ticket = "%s-%s" % (command, phase)
        proc = self.cli(command, ticket, "--phase", phase,
                        "--spec", "docs/spec.md",
                        "--ticket", ".scratch/f/01.md",
                        "--plan", "docs/plan.md")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return ticket

    def test_late_bootstrap_recovers_via_public_commands(self):
        for command in ("start", "adopt"):
            for phase in ("implementation", "review"):
                with self.subTest(command=command, phase=phase):
                    self._bootstrap_recovery_case(command, phase)

    def _bootstrap_recovery_case(self, command, phase):
        ticket = self._late_ticket(command, phase)

        # -- the scaffold is an explicit, unresolved bootstrap recovery ------
        data = self._state_of(ticket)
        self.assertEqual(data["workflow_version"], 2)
        self.assertEqual(data["phase"], phase)  # requested phase unchanged
        self.assertNotIn("upgrade", data)  # no invented conversion facts
        self.assertNotIn("from_version", data.get("upgrade") or {})
        self.assertEqual(data["recovery"], {"kind": "bootstrap"})
        self.assertTrue(data["escalation"]["required"])
        self.assertEqual(data["escalation"]["scope"], "machine")
        self.assertEqual(data["escalation"]["previous_status"], "active")
        self.assertEqual(data["escalation"]["interrupted_phase"], phase)
        interrupted = data["escalation"]["interrupted_action"]
        self.assertEqual(set(interrupted), {"role", "action", "task"})
        self.assertEqual(interrupted["role"],
                         "reviewer" if phase == "review" else "ticket-executor")
        self.assertIsNone(interrupted["task"])
        self.assertEqual(data["status"], "escalation_required")
        self.assertEqual(data["next_action"]["role"], "workflow-bootstrap")
        # Source references are preserved, never copied or dropped.
        self.assertEqual(data["source_artifacts"]["spec"]["path"],
                         "docs/spec.md")
        self.assertEqual(data["source_artifacts"]["ticket"]["path"],
                         ".scratch/f/01.md")
        self.assertEqual(data["source_artifacts"]["plan"]["path"],
                         "docs/plan.md")
        # Task 1's predicate reads this exact shape as a bootstrap recovery.
        self.assertEqual(workflow_v2.recovery_kind(data), "bootstrap")

        # During the recovery window validate still reports the missing
        # retained-phase contracts (the scaffold is never executor-ready),
        # but the coherent workflow-bootstrap route is not route corruption.
        check = self.cli("validate", ticket)
        self.assertEqual(check.returncode, 1, check.stdout + check.stderr)
        self.assertIn("ERRORS PRESENT", check.stdout)
        self.assertNotIn("route corruption", check.stdout)
        # The carve-out is not a bypass: a tampered executor route on the
        # bootstrap State is still reported as corruption.
        data["next_action"]["role"] = "ticket-executor"
        state.save_file(
            os.path.join(self._work(ticket), "state.yaml"), data)
        tampered = self.cli("validate", ticket)
        self.assertEqual(tampered.returncode, 1,
                         tampered.stdout + tampered.stderr)
        self.assertIn("route corruption", tampered.stdout)
        data["next_action"]["role"] = "workflow-bootstrap"
        state.save_file(
            os.path.join(self._work(ticket), "state.yaml"), data)

        # -- unresolved: resume names the resolver; completion rejects --------
        before = self._bytes_of(ticket)
        brief = self.cli("resume", ticket)
        self.assertEqual(brief.returncode, 1, brief.stdout + brief.stderr)
        self.assertIn("workflow-bootstrap", brief.stdout)
        self.assertIn("unresolved escalation", brief.stdout)

        done = self.cli("complete-task", ticket)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("escalation", done.stderr.lower())
        self.assertEqual(self._bytes_of(ticket), before)

        # -- the recovery cannot be cleared before the contracts exist --------
        blocked = self.cli("escalate", ticket, "--clear", "--resolution",
                           self.RESOLUTION)
        self.assertEqual(blocked.returncode, 1, blocked.stdout + blocked.stderr)
        self.assertEqual(self._bytes_of(ticket), before)

        # -- the public recovery sequence (senior, via public commands) -------
        head = self._git("rev-parse", "HEAD").stdout.strip()
        self._write_for(ticket, "evidence.md",
                        valid_evidence(ticket, 1, head))
        with open(os.path.join(self._work(ticket), "evidence.md"), "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
        self._write_for(ticket, "evidence-audit.md",
                        valid_audit(ticket, "sufficient", 1, digest))
        gate = self.cli("set-gate", ticket, "--gate", "sufficient",
                        "--round", "1")
        self.assertEqual(gate.returncode, 0, gate.stdout + gate.stderr)

        plan_name = "plan-%s.md" % ticket
        with open(os.path.join(self.root, plan_name), "w", encoding="utf-8",
                  newline="") as fh:
            fh.write(valid_plan(ticket, 1))
        register = self.cli("register-plan", ticket, "--path", plan_name,
                            "--total", "1")
        self.assertEqual(register.returncode, 0,
                         register.stdout + register.stderr)

        self._write_for(ticket, "decision.md", "# Decision - %s\n" % ticket)

        if command == "adopt":
            # The adoption checkpoint gates the clear: until a senior actually
            # confirms all six items, the retained phase is not restored.
            unconfirmed = self.cli("escalate", ticket, "--clear",
                                   "--resolution", self.RESOLUTION)
            self.assertEqual(unconfirmed.returncode, 1,
                             unconfirmed.stdout + unconfirmed.stderr)
            self.assertIn("adoption checkpoint", unconfirmed.stderr)
            self.assertTrue(
                self._state_of(ticket)["escalation"]["required"])

            # The senior confirms all six items (the same State confirmation
            # the dirty-adoption fixture models); the clear still checks it.
            data = self._state_of(ticket)
            data["adoption_checkpoint"] = {
                name: True for name in workflow_v2.ADOPTION_CONFIRMATIONS}
            state.save_file(
                os.path.join(self._work(ticket), "state.yaml"), data)

        if phase == "review":
            # At a review-phase bootstrap the retained implementation is
            # historically complete: the senior records the reconstructed
            # completion history before the checked clear (the same
            # reconciliation Task 1's pending-review fixture models).
            data = self._state_of(ticket)
            data["implementation"]["current_task"] = 1
            data["implementation"]["completed_tasks"] = [1]
            state.save_file(
                os.path.join(self._work(ticket), "state.yaml"), data)

        # The clear is a transfer boundary (HARDEN-007): the retained
        # implementation/review phase needs a concrete handoff before it.
        data = self._state_of(ticket)
        head = self._git("rev-parse", "HEAD").stdout.strip()
        self._write_for(ticket, "handoff.md", valid_handoff(
            ticket, "main", head,
            artifacts="- Evidence: evidence.md (round 1)\n"
                      "- Evidence audit: evidence-audit.md (gate sufficient)\n"
                      "- Decision: decision.md\n"
                      "- Plan: %s (registered)\n"
                      "- Review: none (no verdict recorded yet)"
                      % data["source_artifacts"]["plan"]["path"]))

        # -- the referenced clear restores the retained phase -----------------
        clear = self.cli("escalate", ticket, "--clear", "--resolution",
                         self.RESOLUTION)
        self.assertEqual(clear.returncode, 0, clear.stdout + clear.stderr)
        data = self._state_of(ticket)
        self.assertFalse(data["escalation"]["required"])
        self.assertEqual(data["phase"], phase)
        self.assertEqual(data["status"], "active")
        # The cleared recovery grants nothing further (the predicate
        # re-derives from the live State), and the clear resolves the
        # self-extinguishing bootstrap marker (unknown keys would survive).
        self.assertIsNone(workflow_v2.recovery_kind(data))
        self.assertIsNone(data["recovery"]["kind"])

        if phase == "implementation":
            # Ordinary execution proceeds.
            self.assertEqual(data["next_action"]["role"], "ticket-executor")
            self.assertEqual(data["next_action"]["task"], 1)
            done = self.cli("complete-task", ticket)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertEqual(
                self._state_of(ticket)["implementation"]["current_task"], 1)
        else:
            # Pending review proceeds: the v2 reviewer route, verdict pending.
            self.assertEqual(data["next_action"]["role"], "reviewer")
            self.assertEqual(data["review"]["verdict"], "pending")
            check = self.cli("validate", ticket)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
            self.assertIn("no ERROR findings", check.stdout)

        # The marker is self-extinguishing: after the clear, an ordinary
        # escalation expects the phase's own senior resolver again. Validate
        # reports no route corruption for that contract-correct State (it
        # still reports the execution-phase status blocker), and a stale
        # workflow-bootstrap route is corruption once more.
        esc = self.cli("escalate", ticket, "--scope", "machine",
                       "--reason", "ordinary follow-up block")
        self.assertEqual(esc.returncode, 0, esc.stdout + esc.stderr)
        data = self._state_of(ticket)
        self.assertIsNone(data["recovery"]["kind"])
        self.assertEqual(data["next_action"]["role"], "technical-decision")
        check = self.cli("validate", ticket)
        self.assertNotIn("route corruption", check.stdout)
        data["next_action"]["role"] = "workflow-bootstrap"
        state.save_file(
            os.path.join(self._work(ticket), "state.yaml"), data)
        stale = self.cli("validate", ticket)
        self.assertEqual(stale.returncode, 1, stale.stdout + stale.stderr)
        self.assertIn("route corruption", stale.stdout)


if __name__ == "__main__":
    unittest.main()