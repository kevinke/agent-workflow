"""Lint for the kit's role skills: state mutations must go through the CLI.

Since TICKET-010, `ai-workflow advance/set-gate/complete-task/claim/escalate`
are the sanctioned way to mutate workflow state. The role skills must teach
agents to call the CLI, never to hand-edit `state.yaml` state-machine fields
(TICKET-011). This test locks that in.
"""

import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import contracts  # noqa: E402
import main  # noqa: E402
import mutate  # noqa: E402
import review_boundary  # noqa: E402
import skills  # noqa: E402

# this file: scripts/ai-workflow/tests/test_skills.py -> 4 levels up to kit root.
_KIT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SKILLS_DIR = os.path.join(_KIT_ROOT, ".agents", "skills")

# Phrasings that mean "hand-edit the state machine directly" — banned.
BANNED = [
    "Update `state.yaml`",
    "set `evidence.gate`",
    "advance `phase` to",
    "clear `next_action` in state.yaml",
    "increment `evidence.round`",
]

# Instructions that make the *reviewer* write or commit a live record — the exact
# gap HARDEN-011 closes, so they must not survive in the reviewer entry point.
# Compared case-insensitively: an instruction reworded with a capital first letter
# ("Commit live records per PROTOCOL before stopping.") is the same defect, not a
# new phrasing, so the ban has to catch it wherever it is capitalized.
LIVE_WRITE_INSTRUCTIONS = [
    "Commit per",
    "Commits and rollback",
    "git commit",
    "Write `review.md`",
    "Write `handoff.md`",
    "commit live",
    "Commit live records",
    "commit the live",
    "commit your live",
    "write the live record",
    "writes the live record",
]

# Limit statements that HARDEN-011 forbids softening. Compared on normalized
# whitespace because the protocol wraps its prose.
PROTOCOL_LIMITS = [
    "Independent context and a final clean diff alone do not establish isolation.",
    "Copying alone, a prompt-only prohibition or a restriction the unrestricted "
    "verifier can undo is not evidence of enforcement.",
    "Sharing writable Git metadata with the live tree is not an isolated snapshot.",
    "It supplies no technical judgment and performs no source repair or phase "
    "transition during publication.",
    "Review provenance cannot prove acceptance or reconstruct past transient writes.",
    "Historical reviews keep their original binding semantics; do not fabricate "
    "isolation claims for them.",
]

# The two honest limits of the published mechanism, pinned as written. Losing one,
# or replacing it with a friendlier promise, is the rot this pins against.
HONEST_LIMITS = [
    "A publication consumes its context. `state.yaml` and `handoff.md` are "
    "captured inputs, so the currentness check refuses a second publication from "
    "one prepared context: each verdict needs a fresh `prepare-review` run and a "
    "fresh independent review of anything that changed.",
    "Journal recovery is deliberately conservative. When an interrupted "
    "transaction cannot hand its own bytes back, the context stays blocked and "
    "there is no operator-facing command to clear it; discarding that context and "
    "preparing a fresh snapshot is the only route, and nothing about that refusal "
    "publishes a verdict.",
]

# No operator-facing command clears a journal-blocked context, so no document may
# name one either.
INVENTED_RECOVERY_COMMANDS = [
    "unblock",
    "unblock-review-context",
    "recover-review-context",
    "clear-review-context",
    "reset-review-context",
    "force-publication",
]

# adapters/codex/windows.md, pinned both ways: the session stays unsupported, and
# the boundary's actual availability on this host is never presented as a blocker.
WINDOWS_VERDICTS = [
    "Isolated review support for this adapter's sessions: not established",
    "**native Windows sessions and Codex Desktop/MCP are unsupported for isolated "
    "reviewer verification** until their actual host tool-write restriction is "
    "separately demonstrated on the host and build in use.",
    "never an automatic permission weakening, never a model-session retry, and "
    "never a passing isolated verdict from a session that could not demonstrate "
    "denial.",
    "The profile this project has demonstrated is bubblewrap (`linux-bwrap-v1`) "
    "inside WSL Ubuntu-24.04 driven by a **Windows** coordinator through "
    "`wsl.exe --exec`",
    "`ai-workflow run-review` invoked from native Windows Python on this machine "
    "does reach an enforced boundary and does write the receipts a guarded "
    "`set-review` validates against",
    "the workflow commands never start at all: the session produces no "
    "`meta/runs/` receipt, no `meta/preflight.json`, no candidate report and "
    "nothing else publishable",
    "The evidence for the supported route is "
    "[../local-review.md](../local-review.md), which records that measurement — "
    "that document, not this runbook, is the evidence source for support claims.",
]

# The refuted claim: `linux-bwrap-v1` is reachable from this Windows host through
# WSL, so no document may predict a blocker here as this machine's practical case.
WINDOWS_FALSE_CLAIMS = ["only provides inside WSL"]

# .ai/workflow/ARTIFACTS.md: what publication actually compares, and what stays a
# reviewer-authored claim. "In any field" overstates the first and hides the second.
ARTIFACTS_RECEIPT_SCOPE = [
    "publication refuses a provenance claim that disagrees with the persisted "
    "receipt in every field the supervisor actually records — each cited run's "
    "`kind`, `argv`, `exit_code`, `stdout_sha256`, `stderr_sha256`, "
    "`snapshot_before` and `snapshot_after` plus its recorded `profile`, the "
    "captured context, manifest and input identities, and the persisted boundary "
    "evidence — together with the rule that no recorded receipt may go uncited.",
    "Fields the receipts cannot corroborate stay reviewer-authored claims, and "
    "publication checks their shape, never their truth: the `limits` list, the "
    "inner commands a run's `argv` goes on to invoke, and a probe's "
    "`before_sha256`/`after_sha256` (a receipt names the observed paths, not "
    "per-path content hashes).",
    "and `deleted` is true exactly when `after_sha256` is null",
]

ARTIFACTS_FALSE_CLAIMS = ["in any field"]

# .ai/workflow/PROTOCOL.md: the Windows gap is scoped to a Windows-*native*
# boundary. The demonstrated host is driven by a Windows coordinator, so "why
# Windows is not [demonstrated]" would contradict the supported configuration.
PROTOCOL_ADAPTER_SCOPE = [
    "`adapters/local-review.md` records the host actually demonstrated (a Windows "
    "coordinator driving `bwrap` through WSL) and `adapters/codex/windows.md` "
    "records why no **Windows-native boundary** is",
    "That is a claim about the session's restriction, not about the boundary's "
    "availability",
]

PROTOCOL_FALSE_SCOPE = ["records why Windows is not"]

ISOLATION_SECTION = 'Reviewer verification isolation and publication'

# A guarded publication refuses a report whose cited runs do not distinguish a
# baseline from a probe (`review_publication._validate_runs`, over
# `review_boundary.KINDS`), so the rule belongs on the surfaces an agent reads
# before authoring: the scaffold it copies, the protocol that routes it, and the
# contract that owns the key list.
RUN_KIND_PLACES = [
    ((".ai", "workflow", "templates", "review.md"),
     "A guarded publication needs both kinds of run named: `runs` must carry at "
     "least one `baseline` acceptance run **and** at least one `probe` run",
     "a baseline-only review is unpublishable however honest it is"),
    ((".ai", "workflow", "PROTOCOL.md"),
     "a guarded publication refuses a report whose cited runs do not distinguish "
     "a `baseline` acceptance run from a `probe` run, so both kinds have to be "
     "named and no recorded receipt may go uncited", None),
    ((".ai", "workflow", "ARTIFACTS.md"),
     "the list has to distinguish the two kinds — at least one `baseline` "
     "acceptance run and at least one `probe` run", None),
]

# The checkpoint-handoff entry gate, pinned both ways. It must stay scoped to
# ordinary phase work with the documented publication exception reachable, and it
# must keep the limit that a mechanical checkpoint-handoff supplies no technical
# verdict. `HANDOFF_UNSCOPED_GATE` is the dead-end phrasing BLOCKING-1 measured:
# read literally it handed the role back at step 2 and made the ticket's
# publication mechanism unreachable through the documented route.
HANDOFF_UNSCOPED_GATE = "`checkpoint-handoff`. If not, hand back."
HANDOFF_VERDICT_LIMIT = "supplies no technical verdict"
HANDOFF_VERDICT_WIDENINGS = [
    "supplies the technical verdict",
    "authors the verdict",
    "writes its own verdict",
    "a verdict of its own",
]

# An installed target never receives `adapters/` (init installs `.ai/workflow/`
# only), so the runbooks have to be pointed at where they do live, and the host
# answer an installed target acts on has to come from its own preflight record.
RUNBOOK_LOCATED = "live in the **ai-workflow source repository**"
PREFLIGHT_IS_THE_HOST_ANSWER = [
    "the runtime answer for any host is the prepared",
    "context's own `meta/preflight.json`, which either records an enforced "
    "boundary or fails closed with a named blocker and no receipt",
]
PREPARATION_OWNER = "is run by the trusted coordinator that also performs the"
STRAY_ARTIFACT_ROUTE = "removing or ignoring the stray artifact and running"

_SHA256_LITERAL = re.compile(r"[0-9a-f]{64}\Z")
_OPTION_TOKEN = re.compile(r"--[a-z][a-z-]*")


def _flat(text):
    return " ".join(text.split())


def _sentences(text):
    """Sentence-ish slices of flattened prose, for co-occurrence claims.

    A claim is only contradicted by a *specific* sentence, so a check like "no
    sentence says this host reports a blocker" needs the sentences, not the file.
    """
    return [part.strip() for part in re.split(r"(?<=[.;!])\s+", _flat(text))
            if part.strip()]


def _doc(*parts):
    path = os.path.join(_KIT_ROOT, *parts)
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _template_provenance(template):
    """The fenced JSON draft under the reserved heading of the shipped template.

    Read from the template itself, so the test compares the document against
    `contracts` rather than against a second hand-written key list.
    """
    marker = re.compile(r"^## %s\s*$" % re.escape(contracts.PROVENANCE_HEADING),
                        re.M)
    heading = marker.search(template)
    if heading is None or len(marker.findall(template)) != 1:
        raise AssertionError(
            "the template must reserve exactly one %r heading, found %d"
            % (contracts.PROVENANCE_HEADING, len(marker.findall(template))))
    tail = template[heading.end():]
    following = re.search(r"^## ", tail, re.M)
    if following is not None:
        tail = tail[:following.start()]
    blocks = re.findall(r"^```json\n(.*?)\n```", tail, re.S | re.M)
    if len(blocks) != 1:
        raise AssertionError("the reserved section holds %d fenced json blocks, "
                             "expected 1" % len(blocks))
    claim = json.loads(blocks[0])
    if not isinstance(claim, dict):
        raise AssertionError("the template provenance is not a JSON map")
    return claim


class SkillsLintTest(unittest.TestCase):
    def _skills(self):
        return sorted(os.listdir(SKILLS_DIR))

    def _text(self, skill):
        with open(os.path.join(SKILLS_DIR, skill, "SKILL.md"), encoding="utf-8") as fh:
            return fh.read()

    def test_no_skill_instructs_hand_editing_state(self):
        for skill in self._skills():
            with self.subTest(skill=skill):
                text = self._text(skill)
                for phrase in BANNED:
                    self.assertNotIn(
                        phrase, text,
                        "%s still instructs %r (use the ai-workflow CLI instead)" % (skill, phrase))

    def test_every_skill_references_the_cli(self):
        for skill in self._skills():
            with self.subTest(skill=skill):
                self.assertIn("ai-workflow", self._text(skill),
                              "%s never references the ai-workflow CLI" % skill)

    def test_install_skills_copies_bundle_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            written = skills.install_skills(tmp)
            self.assertEqual(len(written), len(skills.KIT_SKILLS))
            for name in skills.KIT_SKILLS:
                self.assertTrue(os.path.exists(
                    os.path.join(tmp, ".agents", "skills", name, "SKILL.md")), name)
            # Second run is a true no-op (nothing rewritten).
            self.assertEqual(skills.install_skills(tmp), [])

    def test_install_skills_updates_changed_skill_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills.install_skills(tmp)
            dst = os.path.join(tmp, ".agents", "skills", "repo-scout", "SKILL.md")
            with open(dst, "w", encoding="utf-8") as fh:
                fh.write("stale copy\n")
            written = skills.install_skills(tmp)
            self.assertIn(dst, written)
            with open(dst, encoding="utf-8") as fh:
                self.assertNotEqual(fh.read(), "stale copy\n")

    # -- the eight-skill bundle includes the Reviewer ------------------------

    def test_kit_ships_eight_skills_including_reviewer(self):
        self.assertEqual(len(skills.KIT_SKILLS), 8)
        self.assertIn("reviewer", skills.KIT_SKILLS)
        for name in skills.KIT_SKILLS:
            self.assertTrue(
                os.path.isfile(os.path.join(SKILLS_DIR, name, "SKILL.md")), name)

    def test_install_skills_installs_reviewer(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills.install_skills(tmp)
            self.assertTrue(os.path.isfile(os.path.join(
                tmp, ".agents", "skills", "reviewer", "SKILL.md")))

    def test_help_and_install_text_report_eight_role_skills(self):
        self.assertIn("eight role skills", main.USAGE)
        self.assertNotIn("seven", main.USAGE)
        with tempfile.TemporaryDirectory() as tmp:
            skills.install_skills(tmp)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = main.cmd_install_skills(["install-skills", tmp], tmp)
            self.assertEqual(code, 0)
            self.assertIn("eight role skills", buf.getvalue())

    # -- HARDEN-011: every reviewer entry point routes through the boundary ---

    def test_reviewer_entry_points_require_boundary(self):
        """The reviewer role is never told to write or commit a live record.

        Skills stay thin pointers: they name the commands and route to the
        protocol, and the protocol keeps the business rules.
        """
        text = self._text("reviewer")
        for needle in ("prepare-review", "run-review", "--review-context",
                       "--report", "--handoff", ISOLATION_SECTION, "candidate",
                       "no live commit"):
            self.assertIn(needle, text,
                          "the reviewer skill never names %r" % needle)
        for phrase in LIVE_WRITE_INSTRUCTIONS:
            self.assertNotIn(phrase.lower(), text.lower(),
                             "the reviewer skill still instructs %r" % phrase)
        for line in text.splitlines():
            if "set-review" in line and "--verdict" in line:
                self.assertIn("--review-context", line,
                              "the reviewer skill offers an unguarded set-review: "
                              "%s" % line)
        # Thin pointer: the skill must not restate the protocol's limit rules.
        flat = _flat(text)
        for sentence in PROTOCOL_LIMITS:
            self.assertNotIn(_flat(sentence), flat,
                             "the reviewer skill restates a protocol limit rule: %r"
                             % sentence)

        handoff = self._text("checkpoint-handoff")
        for needle in ("--review-context", ISOLATION_SECTION,
                       "Do not write `review.md`"):
            self.assertIn(needle, handoff,
                          "the checkpoint-handoff skill never names %r" % needle)
        self.assertIn("phase transition during publication", _flat(handoff),
                      "the checkpoint-handoff skill still lets publication "
                      "advance the phase")

        roles = _doc(".ai", "workflow", "ROLES.md")
        reviewer = roles.split("## reviewer")[1].split("## checkpoint-handoff")[0]
        self.assertIn(ISOLATION_SECTION, reviewer)
        self.assertIn("candidate", reviewer)
        self.assertIn("writes no live record", _flat(reviewer),
                      "the reviewer routing entry still makes the reviewer the "
                      "author of a live record")
        for phrase in LIVE_WRITE_INSTRUCTIONS:
            self.assertNotIn(phrase.lower(), reviewer.lower(),
                             "the reviewer routing entry instructs %r" % phrase)

        # The public command surface documents the guarded options it really has.
        for needle in ("prepare-review", "run-review", "--review-context"):
            self.assertIn(needle, main.USAGE,
                          "the CLI usage block never names %r" % needle)
        readme = _doc("README.md")
        for needle in ("prepare-review", "run-review", "--review-context"):
            self.assertIn(needle, readme,
                          "README's command overview never names %r" % needle)

    def test_protocol_and_template_keep_the_limit_statements(self):
        """The protocol documents the real commands and keeps every limit."""
        protocol = _flat(_doc(".ai", "workflow", "PROTOCOL.md"))
        for sentence in PROTOCOL_LIMITS:
            self.assertIn(sentence, protocol,
                          "PROTOCOL.md lost a limit statement: %r" % sentence)
        self.assertNotIn("pending HARDEN-011", protocol,
                         "PROTOCOL.md still calls the mechanism pending")
        for needle in ("prepare-review", "run-review", "--review-context",
                       "linux-bwrap-v1", "blocker"):
            self.assertIn(needle, protocol,
                          "PROTOCOL.md never names %r" % needle)
        # The adapter pointer must scope the undemonstrated thing precisely: a
        # Windows-*native* boundary, not Windows itself, whose coordinator is the
        # one the supported profile is demonstrated on.
        for sentence in PROTOCOL_ADAPTER_SCOPE:
            self.assertIn(_flat(sentence), protocol,
                          "PROTOCOL.md lost the adapter scope sentence: %r"
                          % sentence)
        for claim in PROTOCOL_FALSE_SCOPE:
            self.assertNotIn(claim, protocol,
                             "PROTOCOL.md again writes off the whole of Windows, "
                             "which is the supported coordinator: %r" % claim)

        artifacts = _flat(_doc(".ai", "workflow", "ARTIFACTS.md"))
        self.assertNotIn("pending HARDEN-011", artifacts,
                         "the provenance contract still calls enforcement pending")
        self.assertIn("--review-context", artifacts)
        self.assertIn("Structural report checks cannot attest that a host denied "
                      "writes", artifacts)

        template = _doc(".ai", "workflow", "templates", "review.md")
        self.assertIn("Isolation provenance", template)
        self.assertIn("draft", template.lower(),
                      "the template provenance is not a marked draft placeholder")

        # The adapter docs say plainly what is not supported.
        windows = _doc("adapters", "codex", "windows.md")
        self.assertIn("CreateProcess", windows,
                      "the observed Windows launch diagnostics were laundered away")
        self.assertIn("unsupported", windows.lower())
        local = _doc("adapters", "local-review.md")
        for needle in ("linux-bwrap-v1", "EROFS", "ENETUNREACH", "unsupported"):
            self.assertIn(needle, local,
                          "the local adapter doc never records %r" % needle)


    def test_honest_limits_stay_stated_and_no_recovery_is_invented(self):
        """The two published-mechanism limits are pinned where agents read them.

        HARDEN-011's honest limits are that a publication *consumes* its prepared
        context (one verdict per context, because `state.yaml` and `handoff.md` are
        captured inputs) and that a journal-blocked context has **no**
        operator-facing unblock command. A friendlier sentence — or an invented
        `unblock`/`recover` command — sends an agent to re-publish from a consumed
        context, which is the failure these documents exist to prevent.
        """
        protocol = _flat(_doc(".ai", "workflow", "PROTOCOL.md"))
        for sentence in HONEST_LIMITS:
            self.assertIn(_flat(sentence), protocol,
                          "PROTOCOL.md dropped or reworded an honest limit: %r"
                          % sentence)
        self.assertIn("Two limits of the published mechanism stay stated rather "
                      "than implied away", protocol)

        reviewer = _flat(self._text("reviewer"))
        self.assertIn("a prepared context publishes at most one verdict", reviewer,
                      "the reviewer skill no longer says a context is consumed by "
                      "one verdict")
        handoff = _flat(self._text("checkpoint-handoff"))
        self.assertIn("never a re-used context", handoff,
                      "the checkpoint-handoff skill offers a re-used context")
        local = _flat(_doc("adapters", "local-review.md"))
        self.assertIn("A publication consumes its context: each verdict needs its "
                      "own prepared context.", local,
                      "the supported adapter no longer says a context is consumed")
        self.assertIn("There is **no operator-facing command to clear a "
                      "journal-blocked context**", local,
                      "the supported adapter promises an unblock route")
        self.assertIn("publication consumes its context — one verdict per prepared "
                      "context", _flat(main.USAGE),
                      "the CLI usage no longer says a context is consumed")

        surface = [("PROTOCOL.md", _doc(".ai", "workflow", "PROTOCOL.md")),
                   ("ROLES.md", _doc(".ai", "workflow", "ROLES.md")),
                   ("ARTIFACTS.md", _doc(".ai", "workflow", "ARTIFACTS.md")),
                   ("local-review.md", _doc("adapters", "local-review.md")),
                   ("windows.md", _doc("adapters", "codex", "windows.md")),
                   ("README.md", _doc("README.md")),
                   ("reviewer skill", self._text("reviewer")),
                   ("checkpoint-handoff skill", self._text("checkpoint-handoff")),
                   ("CLI usage", main.USAGE)]
        for label, text in surface:
            for command in INVENTED_RECOVERY_COMMANDS:
                self.assertNotIn(command, text.lower(),
                                 "%s offers the non-existent command %r; a "
                                 "journal-blocked context has no unblock route"
                                 % (label, command))

    def test_shipped_template_provenance_matches_the_contract(self):
        """The draft the kit ships satisfies the validator it is filled into.

        The key sets come from `contracts` and the values from the template's own
        fenced block, so a key renamed or dropped on either side breaks this test,
        and so does a draft example that violates the deletion-pairing rule.
        """
        template = _doc(".ai", "workflow", "templates", "review.md")
        claim = _template_provenance(template)
        self.assertEqual(set(claim), set(contracts.PROVENANCE_KEYS),
                         "the template's reserved section and contracts.py no "
                         "longer agree on the provenance keys")
        self.assertTrue(claim["runs"], "the template ships no run example")
        for run in claim["runs"]:
            self.assertEqual(set(run), set(contracts.PROVENANCE_RUN_KEYS),
                             "the template's run example and contracts.py no "
                             "longer agree on the run keys")
        self.assertEqual(set(claim["boundary"]),
                         set(contracts.PROVENANCE_BOUNDARY_KEYS),
                         "the template's boundary example and contracts.py no "
                         "longer agree on the boundary keys")
        self.assertTrue(claim["probe_changes"],
                        "the template ships no probe_changes example")
        for change in claim["probe_changes"]:
            self.assertEqual(set(change), set(contracts.PROVENANCE_PROBE_KEYS),
                             "the template's probe example and contracts.py no "
                             "longer agree on the probe keys")
            # contracts.py refuses a report whose `deleted` disagrees with
            # after_sha256 being null: a draft copied from the template must not
            # be refused for the shape of the shipped example itself.
            self.assertEqual(
                change["deleted"], change["after_sha256"] is None,
                "the template's probe_changes example is not a legal pair: a "
                "path is deleted only when after_sha256 is null (%r)" % (change,))
        self.assertEqual(set(claim["residual_changes"]),
                         set(contracts.PROVENANCE_RESIDUAL_KEYS),
                         "the template's residual example and contracts.py no "
                         "longer agree on the residual keys")

        # An example is not evidence: every identity slot keeps its draft marker
        # and no real-looking hash ships in the file.
        for key in ("reviewed_commit", "context_sha256", "live_manifest_sha256",
                    "snapshot_manifest_sha256", "plan_sha256"):
            self.assertIn("draft", claim[key],
                          "template key %r stopped being a marked placeholder"
                          % key)
        for key in ("preflight_sha256",):
            self.assertIn("draft", claim["boundary"][key],
                          "template key %r stopped being a marked placeholder"
                          % key)
        for run in claim["runs"]:
            for key in ("run_id", "argv", "stdout_sha256", "stderr_sha256",
                        "snapshot_before", "snapshot_after"):
                self.assertIn("draft", json.dumps(run[key]),
                              "template run key %r stopped being a marked "
                              "placeholder" % key)
        for change in claim["probe_changes"]:
            self.assertIn("draft", change["path"],
                          "the template's probe path stopped being a marked "
                          "placeholder")
            for key in ("before_sha256", "after_sha256"):
                value = change[key]
                self.assertTrue(value is None or "draft" in value,
                                "template probe key %r stopped being a marked "
                                "placeholder" % key)
        self.assertNotRegex(
            template, r"[0-9a-f]{64}",
            "the shipped template carries a full SHA-256: a draft must never "
            "look like a receipt")

    def test_shipped_template_runs_name_the_pair_publication_demands(self):
        """The scaffold models the run set a guarded publication cites.

        `review_publication._validate_runs` refuses a report whose cited runs do
        not distinguish both kinds, so a `runs` example carrying only a baseline
        teaches a reviewer to author a report the shipped mechanism rejects — the
        reviewer learns the rule from a refusal instead of from the template. The
        draft values stay placeholders on purpose (`contracts` refuses
        placeholders: an unfilled scaffold proves nothing), so what is pinned is
        every run-level structural rule `contracts.parse_artifact` applies, read
        from `contracts`' own constants.
        """
        template = _doc(".ai", "workflow", "templates", "review.md")
        runs = _template_provenance(template)["runs"]
        kinds = [run["kind"] for run in runs]
        self.assertEqual(sorted(kinds), sorted(contracts.PROVENANCE_RUN_KINDS),
                         "the template's `runs` example must name one baseline "
                         "and one probe run: guarded publication refuses a "
                         "report that does not distinguish both kinds (%r)"
                         % (kinds,))
        self.assertEqual(set(kinds), set(review_boundary.KINDS),
                         "the template's run kinds and the boundary's own kinds "
                         "no longer agree (%r vs %r)"
                         % (kinds, review_boundary.KINDS))
        for kind in contracts.PROVENANCE_RUN_KINDS:
            self.assertEqual(kinds.count(kind), 1,
                             "the template ships %d %r run examples, expected 1"
                             % (kinds.count(kind), kind))
        for index, run in enumerate(runs):
            owner = "runs[%d]" % index
            self.assertEqual(set(run), set(contracts.PROVENANCE_RUN_KEYS),
                             "the template's %s example and contracts.py no "
                             "longer agree on the run keys" % owner)
            self.assertIsInstance(run["run_id"], str,
                                  "field %r must declare a run_id" % owner)
            self.assertTrue(run["run_id"],
                            "field %r must declare a non-empty run_id" % owner)
            self.assertIn(run["kind"], contracts.PROVENANCE_RUN_KINDS,
                          "field %r must be a %s run, got %r"
                          % (owner, " or ".join(contracts.PROVENANCE_RUN_KINDS),
                             run["kind"]))
            argv = run["argv"]
            self.assertTrue(isinstance(argv, list) and argv
                            and all(isinstance(item, str) and item
                                    for item in argv),
                            "field %r.argv must be a non-empty list of arguments"
                            % owner)
            self.assertIsInstance(run["exit_code"], int,
                                  "field %r.exit_code must be an integer, got %r"
                                  % (owner, run["exit_code"]))
            self.assertNotIsInstance(run["exit_code"], bool,
                                     "field %r.exit_code must be an integer, not "
                                     "a boolean" % owner)
            for key in ("stdout_sha256", "stderr_sha256", "snapshot_before",
                        "snapshot_after"):
                value = run[key]
                # Each is a receipt slot: a real digest or a marked draft that an
                # author replaces, never prose no hash can stand in for.
                self.assertTrue(isinstance(value, str)
                                and (_SHA256_LITERAL.match(value)
                                     or "draft" in value),
                                "field %r.%s is neither a SHA-256 nor a marked "
                                "draft: %r" % (owner, key, value))

    def test_run_kind_rule_is_stated_where_an_agent_reads_it(self):
        """The both-kinds rule is documented before authoring, not only in code.

        Three surfaces, in the order a reviewer meets them: the scaffold it
        copies, the protocol that routes the work, the contract that owns the key
        list. A refusal the agent can only predict from the source is the defect.
        """
        for parts, sentence, extra in RUN_KIND_PLACES:
            with self.subTest(document=os.path.join(*parts)):
                flat = _flat(_doc(*parts))
                self.assertIn(_flat(sentence), flat,
                              "%s never states that a report must name both run "
                              "kinds: %r" % (os.path.join(*parts), sentence))
                if extra:
                    self.assertIn(_flat(extra), flat,
                                  "%s lost the consequence of the both-kinds "
                                  "rule: %r" % (os.path.join(*parts), extra))

    def test_checkpoint_handoff_gate_keeps_its_own_publication_reachable(self):
        """The entry gate routes ordinary phase work; it never vetoes step 6.

        PROTOCOL.md's routing sentence stays as written — in `review` the route is
        `reviewer`, and `next_action` still says `reviewer` after a verdict is
        published — so a bare "if not, hand back" gate made the role PROTOCOL §9
        names as the publisher refuse the very step the same file instructs. Pinned
        both ways: the scoped gate with its publication exception is stated, and
        the unscoped dead-end phrasing is gone. The limit that this role supplies
        no technical verdict stays, so the exception is never read as a licence to
        judge.
        """
        text = self._text("checkpoint-handoff")
        flat = _flat(text)
        self.assertNotIn(HANDOFF_UNSCOPED_GATE, flat,
                         "the checkpoint-handoff gate is unscoped again: read "
                         "literally it hands back before the publication step it "
                         "also requires (%r)" % HANDOFF_UNSCOPED_GATE)
        self.assertIn(HANDOFF_VERDICT_LIMIT, flat,
                      "the checkpoint-handoff skill lost the limit that it "
                      "supplies no technical verdict")
        for phrase in HANDOFF_VERDICT_WIDENINGS:
            self.assertNotIn(phrase, flat,
                             "the publication exception widened into %r: this "
                             "role coordinates the guarded set-review of the "
                             "reviewer's own candidate bytes and judges nothing"
                             % phrase)
        gate = [sentence for sentence in _sentences(text)
                if "hand back" in sentence.lower()]
        self.assertTrue(gate, "the skill's role gate disappeared entirely; the "
                              "route still has to be checked before ordinary "
                              "phase work")
        for sentence in gate:
            self.assertIn("publication", sentence.lower(),
                          "the hand-back gate is stated without its documented "
                          "publication exception, which re-creates the dead end: "
                          "%r" % sentence)
        self.assertIn("guarded publication", flat)
        # Coordination stays exactly the guarded publication: the step still names
        # the trio it runs and nothing else.
        self.assertIn("--review-context", flat)
        self.assertIn("coordinate the guarded publication and nothing else", flat,
                      "the publication step stopped confining this role to "
                      "coordination")

    def test_guarded_options_refusal_names_options_the_cli_accepts(self):
        """Every option the partial-guard message prints is a real option.

        `mutate.set_review`'s parameters are `report_path`/`handoff_path`; the CLI
        spells them `--report`/`--handoff`. The refusal used to derive names from
        the parameters, so following it produced a second refusal —
        `unknown or missing-value option '--report-path'` (rc=2) — and the reader
        never reached the guarded publication.
        """
        cases = (({"review_context": "ctx"}, "--review-context",
                  "--report, --handoff"),
                 ({"review_context": "ctx", "report_path": "r.md"},
                  "--review-context, --report", "--handoff"),
                 ({"report_path": "r.md", "handoff_path": "h.md"},
                  "--report, --handoff", "--review-context"))
        for supplied, got, missing in cases:
            with self.subTest(supplied=sorted(supplied)):
                with tempfile.TemporaryDirectory() as tmp:
                    with self.assertRaises(mutate.MutateError) as caught:
                        mutate.set_review(tmp, "T-DEMO-001", "pass", **supplied)
                message = str(caught.exception)
                self.assertIn("must be supplied together", message)
                self.assertIn("got %s" % got, message,
                              "the refusal misnames the options already given: %s"
                              % message)
                self.assertIn("missing %s" % missing, message,
                              "the refusal misnames the options still owed: %s"
                              % message)
                tokens = _OPTION_TOKEN.findall(message)
                self.assertTrue(tokens,
                                "the refusal names no option at all: %s" % message)
                for token in tokens:
                    _opts, err = main._parse_options([token, "value"],
                                                     main.SET_REVIEW_OPTIONS)
                    self.assertIsNone(
                        err,
                        "%r is not an option set-review accepts, so the refusal "
                        "sends the reader into an unknown-option error: %s"
                        % (token, message))
                self.assertFalse([token for token in tokens
                                  if token.endswith("-path")],
                                 "an internal parameter name leaked into the "
                                 "message: %s" % message)

    def test_installed_docs_point_at_resolvable_guidance_and_named_owners(self):
        """Nothing in an installed target sends a reader to a file it cannot open.

        `init` installs `.ai/workflow/` only, so the host runbooks have to be
        located in the ai-workflow source repository and the runtime host answer
        pointed at the context's own `meta/preflight.json`; the adapter doc has to
        cite committed tests and receipt fields rather than git-ignored working
        notes; `prepare-review` has to name the role that runs it and document the
        fail-closed refusal a stray generated artifact produces; and
        STATE_SCHEMA.md has to document the guarded publication reviewer step 9
        sends agents to.
        """
        protocol = _flat(_doc(".ai", "workflow", "PROTOCOL.md"))
        self.assertIn(RUNBOOK_LOCATED, protocol,
                      "the installed protocol points at adapter runbooks again "
                      "without saying an installed target does not receive them")
        for sentence in PREFLIGHT_IS_THE_HOST_ANSWER:
            self.assertIn(_flat(sentence), protocol,
                          "PROTOCOL.md lost the preflight-is-the-host-answer "
                          "sentence: %r" % sentence)
        self.assertIn(PREPARATION_OWNER, protocol,
                      "`prepare-review` has no documented owner again; the "
                      "reviewer skill sends the snapshot to a coordinator")
        self.assertIn(STRAY_ARTIFACT_ROUTE, protocol,
                      "PROTOCOL.md no longer documents the stray-artifact "
                      "preparation refusal and the route past it")
        self.assertIn("__pycache__", protocol,
                      "the documented preparation blocker lost its concrete case")
        for sentence in PROTOCOL_ADAPTER_SCOPE:
            self.assertIn(_flat(sentence), protocol,
                          "PROTOCOL.md lost the adapter scope sentence: %r"
                          % sentence)
        for claim in PROTOCOL_FALSE_SCOPE:
            self.assertNotIn(claim, protocol,
                             "PROTOCOL.md again writes off the whole of Windows, "
                             "which is the supported coordinator: %r" % claim)

        artifacts = _flat(_doc(".ai", "workflow", "ARTIFACTS.md"))
        self.assertIn("live in the ai-workflow source repository rather",
                      artifacts,
                      "the provenance contract cites adapter runbooks an "
                      "installed target cannot open")

        local = _doc("adapters", "local-review.md")
        self.assertNotIn(".superpowers", local,
                         "the adapter doc cites git-ignored working notes; a "
                         "fresh checkout cannot resolve its evidence")
        for needle in ("test_review_boundary.py", "test_review_publication.py",
                       "InstalledIsolatedReviewLifecycleTest",
                       "meta/preflight.json", "changed_paths", "snapshot_after"):
            self.assertIn(needle, local,
                          "the adapter evidence pointer never names %r" % needle)
        for needle in ("EROFS", "EXDEV", "ENETUNREACH", "bubblewrap 0.9.0",
                       "network_denial_errno=101", "unsupported"):
            self.assertIn(needle, local,
                          "the adapter doc lost a measured number: %r" % needle)

        reviewer = self._text("reviewer")
        coordinator = [sentence for sentence in _sentences(reviewer)
                       if "coordinator" in sentence.lower()]
        self.assertTrue(coordinator,
                        "the reviewer skill sends the snapshot to no coordinator "
                        "at all")
        self.assertTrue(any("checkpoint-handoff" in sentence
                            for sentence in coordinator),
                        "'the coordinator' names no role an agent can find among "
                        "the eight: %r" % coordinator)

        handoff = _flat(self._text("checkpoint-handoff"))
        self.assertIn("prepare-review", handoff,
                      "the role that owns preparation never sees the command in "
                      "its own skill")

        schema = _flat(_doc(".ai", "workflow", "STATE_SCHEMA.md"))
        self.assertNotIn("pending HARDEN-011", schema)
        for needle in ("--review-context", "--report", "--handoff",
                       "required together", "Isolation provenance",
                       "consumes its context"):
            self.assertIn(needle, schema,
                          "STATE_SCHEMA.md's v2 Review binding never documents "
                          "the guarded publication form (%r)" % needle)

    def test_windows_adapter_keeps_the_verdict_without_a_fabricated_blocker(
            self):
        """windows.md stays unsupported for its sessions and true about this host.

        Pinned both ways: the file must keep saying the native Windows / Codex
        session is unsupported, and it must not claim that `run-review` reports a
        blocker on a host whose WSL does provide `bwrap`. The second half matters
        as much as the first — a false "this machine is blocked" sentence routes an
        agent away from the one verification route that works here.
        """
        windows = _doc("adapters", "codex", "windows.md")
        flat = _flat(windows)
        for sentence in WINDOWS_VERDICTS:
            self.assertIn(_flat(sentence), flat,
                          "windows.md lost its verdict or its measured scope: "
                          "%r" % sentence)
        self.assertIn("CreateProcess", windows,
                      "the observed Windows launch diagnostics were laundered away")
        for claim in WINDOWS_FALSE_CLAIMS:
            self.assertNotIn(claim, flat,
                             "windows.md re-asserts the refuted claim %r" % claim)
        for sentence in _sentences(windows):
            lower = sentence.lower()
            self.assertFalse(
                ("named blocker" in lower and
                 ("this machine" in lower or "this host" in lower)),
                "windows.md predicts a blocker for this machine, which its own "
                "evidence contradicts: %r" % sentence)

    def test_artifacts_keeps_the_checked_versus_claimed_distinction(self):
        """ARTIFACTS.md states what receipts corroborate and what they cannot.

        The validator compares the receipt fields `contracts`/`review_publication`
        persist; `limits`, a run's inner commands and a probe's before/after hashes
        stay reviewer-authored claims. Inflating that back to "any field" turns a
        documented limit into a support claim, so both halves are pinned.
        """
        artifacts = _flat(_doc(".ai", "workflow", "ARTIFACTS.md"))
        for sentence in ARTIFACTS_RECEIPT_SCOPE:
            self.assertIn(_flat(sentence), artifacts,
                          "ARTIFACTS.md lost the receipt-scope statement: %r"
                          % sentence)
        for claim in ARTIFACTS_FALSE_CLAIMS:
            self.assertNotIn(claim, artifacts,
                             "ARTIFACTS.md re-inflated the publication check to "
                             "%r: the receipts cannot corroborate every claimed "
                             "field" % claim)
        for sentence in _sentences(_doc(".ai", "workflow", "ARTIFACTS.md")):
            lower = sentence.lower()
            self.assertFalse(
                "before_sha256" in lower and "disagrees with the persisted" in lower,
                "ARTIFACTS.md now presents a probe's content hashes as "
                "receipt-corroborated: %r" % sentence)


if __name__ == "__main__":
    unittest.main()
