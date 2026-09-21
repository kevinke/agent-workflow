"""End-to-end dogfood regression test: the kit testing itself.

Installs the kit into a throwaway repo via the real CLI (`ai-workflow init`),
scaffolds a ticket from the shipped template, then walks one ticket through the
entire phase machine (requirement -> evidence_collection -> evidence_audit ->
followup_evidence -> ... -> done), running the real `ai-workflow validate` gate
at every phase boundary.

This is the regression net for the whole workflow. If the install path, the
template, the state machine, the artifact contracts, or the validate gates break,
this test goes red — independent of any single unit test.

Run (from scripts/ai-workflow/):
    python -m unittest discover -s tests -v
    python tests/test_dogfood.py          (standalone)
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import init as init_mod  # noqa: E402
import state  # noqa: E402

# The real CLI entry point, driven via subprocess so we test the user surface.
KIT_CLI = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")

HANDOFF_SECTIONS = [
    "What was done", "What remains", "Important discoveries",
    "Current failure", "Do not repeat", "Next recommended action",
    "Repository State",
]

TICKET = "TICKET-001"


class DogfoodE2ETest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.work = os.path.join(self.root, ".ai", "work", TICKET)

        code, _out, err = self._cli("init", self.root)
        self.assertEqual(code, 0, err)
        # Dogfood: the ticket is started through the real `start` CLI, not
        # hand-scaffolded — the user-facing entry point is the thing under test.
        code, _out, err = self._cli("start", TICKET, "--title", "dogfood e2e ticket")
        self.assertEqual(code, 0, err)

    def tearDown(self):
        self._tmp.cleanup()

    # -- helpers --------------------------------------------------------------

    def _cli(self, *args):
        proc = subprocess.run(
            [sys.executable, KIT_CLI] + list(args),
            capture_output=True, text=True, cwd=self.root)
        return proc.returncode, proc.stdout, proc.stderr

    def _validate(self):
        code, out, err = self._cli("validate")
        return code, out + err

    def _assert_validate_ok(self, msg="validate must pass"):
        code, out = self._validate()
        self.assertEqual(code, 0, "%s\n%s" % (msg, out))

    def _cli_ok(self, *args):
        """Run the real CLI and require exit 0; return its stdout."""
        code, out, err = self._cli(*args)
        self.assertEqual(code, 0, "%s: %s" % (" ".join(args), err))
        return out

    def _write(self, name, content):
        with open(os.path.join(self.work, name), "w", encoding="utf-8") as fh:
            fh.write(content)

    def _load(self):
        return state.load_file(os.path.join(self.work, "state.yaml"))

    def _save(self, data):
        state.save_file(os.path.join(self.work, "state.yaml"), data)

    def _set(self, **mutations):
        data = self._load()
        data.update(mutations)
        self._save(data)
        return data

    # -- the lifecycle ----------------------------------------------------------

    def test_full_lifecycle_passes_validate_at_every_phase(self):
        # requirement: as scaffolded by `start`.
        self._assert_validate_ok("requirement")

        # evidence_collection (scout collects evidence.md)
        self._write("evidence.md", "## Facts\n- FACT source artifact spec section\n")
        self._cli_ok("advance", TICKET, "--to", "evidence_collection")
        self._assert_validate_ok("evidence_collection")
        code, out, _ = self._cli("status", TICKET)
        self.assertEqual(code, 0)
        self.assertIn("evidence_collection", out)

        # evidence_audit — verdict insufficient opens the evidence loop.
        self._write("evidence-audit.md", "## Sufficiency\n- gate: insufficient\n")
        self._cli_ok("advance", TICKET, "--to", "evidence_audit")
        self._cli_ok("set-gate", TICKET, "--gate", "insufficient", "--round", "1")
        self._assert_validate_ok("evidence_audit (insufficient)")

        # followup_evidence — gate insufficient makes the loop-back branch legal.
        self._cli_ok("advance", TICKET, "--to", "followup_evidence")
        self._assert_validate_ok("followup_evidence")

        # evidence_audit — now sufficient, gate opens the decisionward phases.
        self._cli_ok("advance", TICKET, "--to", "evidence_audit")
        self._cli_ok("set-gate", TICKET, "--gate", "sufficient", "--round", "2")
        self._assert_validate_ok("evidence_audit (sufficient)")

        # technical_decision (senior: decision.md is NOT yet required here).
        self._cli_ok("advance", TICKET, "--to", "technical_decision")
        self._assert_validate_ok("technical_decision")

        # planning (senior: decision.md now required).
        self._write("decision.md", "## Decision\n- approach: build it\n")
        self._cli_ok("advance", TICKET, "--to", "planning")
        self._assert_validate_ok("planning")

        # implementation (cheap executor: task counters progress).
        self._write("progress.md", "## Progress\n- task 1..3 complete\n")
        self._cli_ok("advance", TICKET, "--to", "implementation")
        for _ in range(3):
            self._cli_ok("complete-task", TICKET, "--total", "3")
        self._assert_validate_ok("implementation")

        # review (checkpoint-handoff).
        self._cli_ok("advance", TICKET, "--to", "review")
        self._assert_validate_ok("review")

        # done — `advance` clears next_action automatically.
        self._cli_ok("advance", TICKET, "--to", "done")
        self._assert_validate_ok("done")

    # -- install / idempotency --------------------------------------------------

    def test_init_is_idempotent_and_managed_block_single(self):
        with open(os.path.join(self.root, "AGENTS.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertEqual(text.count(init_mod.BEGIN_MARKER), 1)
        self.assertEqual(text.count(init_mod.END_MARKER), 1)

        code, out, _ = self._cli("init", self.root)
        self.assertEqual(code, 0)
        self.assertIn("idempotent", out)
        with open(os.path.join(self.root, "AGENTS.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), text)

    def test_upgrade_cli_is_noop_when_current(self):
        # The installed protocol ships at the kit's current version, so the
        # explicit upgrade is a no-op through the real CLI.
        code, out, err = self._cli("upgrade")
        self.assertEqual(code, 0, err)
        self.assertIn("nothing to do", out)

    # -- negative regression gates ---------------------------------------------

    def test_gate_violation_at_technical_decision_is_error(self):
        self._write("evidence.md", "facts\n")
        self._write("evidence-audit.md", "audit\n")
        self._set(phase="technical_decision",
                  evidence={"round": 1, "gate": "insufficient"},
                  next_action={"role": "technical-decision",
                               "action": "decide", "task": None})
        code, out = self._validate()
        self.assertNotEqual(code, 0)
        self.assertIn("gate-violating", out)

    def test_done_with_next_action_is_error(self):
        self._write("evidence.md", "facts\n")
        self._write("evidence-audit.md", "audit\n")
        self._write("decision.md", "decision\n")
        self._set(phase="done",
                  evidence={"round": 1, "gate": "sufficient"},
                  next_action={"role": "checkpoint-handoff",
                               "action": "x", "task": None})
        code, out = self._validate()
        self.assertNotEqual(code, 0)
        self.assertIn("phase=done", out)

    def test_current_task_over_total_is_error(self):
        self._write("evidence.md", "facts\n")
        self._write("evidence-audit.md", "audit\n")
        self._write("decision.md", "decision\n")
        self._set(phase="implementation",
                  evidence={"round": 1, "gate": "sufficient"},
                  implementation={"current_task": 5, "total_tasks": 3,
                                  "completed_tasks": []},
                  next_action={"role": "ticket-executor",
                               "action": "implement", "task": 5})
        code, out = self._validate()
        self.assertNotEqual(code, 0)
        self.assertIn("current_task", out)

    def test_missing_decision_at_planning_is_error(self):
        self._write("evidence.md", "facts\n")
        self._write("evidence-audit.md", "audit\n")
        self._set(phase="planning",
                  evidence={"round": 1, "gate": "sufficient"},
                  next_action={"role": "executor-plan",
                               "action": "plan", "task": None})
        code, out = self._validate()
        self.assertNotEqual(code, 0)
        self.assertIn("decision.md", out)

    # -- git discipline (skipped when git is unavailable) -----------------------

    def test_phase_boundary_commits_use_prefix(self):
        if shutil.which("git") is None:
            self.skipTest("git not available")

        # Identity via env vars only — never touch git config.
        env = dict(os.environ)
        env.update({
            "GIT_AUTHOR_NAME": "dogfood", "GIT_AUTHOR_EMAIL": "dogfood@local",
            "GIT_COMMITTER_NAME": "dogfood", "GIT_COMMITTER_EMAIL": "dogfood@local",
        })

        def git(*args):
            return subprocess.run(["git", "-C", self.root] + list(args),
                                  capture_output=True, text=True, env=env)

        self.assertEqual(git("init", "-q").returncode, 0)
        git("add", "-A")
        self.assertEqual(git("commit", "-q", "-m",
                             "ai-workflow(TICKET-001): requirement").returncode, 0)

        self._write("evidence.md", "facts\n")
        self._set(phase="evidence_collection",
                  next_action={"role": "scout",
                               "action": "collect", "task": None})
        git("add", "-A")
        self.assertEqual(git("commit", "-q", "-m",
                             "ai-workflow(TICKET-001): evidence_collection").returncode, 0)

        for line in git("log", "--format=%s").stdout.splitlines():
            self.assertTrue(line.startswith("ai-workflow(TICKET-001): "), line)

        # Committed tree -> validate no longer warns about uncommitted work.
        code, out = self._validate()
        self.assertEqual(code, 0, out)
        self.assertNotIn("uncommitted work", out)


if __name__ == "__main__":
    unittest.main()
