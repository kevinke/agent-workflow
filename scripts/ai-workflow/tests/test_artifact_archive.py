"""Verified export tests (HARDEN-006 Task 2).

`archive-artifacts` turns a v2 Ticket whose bindings are CURRENT into a ZIP
holding the exact raw bytes the workflow bound: a `manifest.json` (format
version 1) plus one member per collected artifact at its repository-relative
path. Every rejection must exit 1, leave no output file behind, and leave the
State and source snapshot byte-identical.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import artifact_archive  # noqa: E402

from v2_support import V2CLITestCase  # noqa: E402

# Plain-probe CRLF lines appended to artifact bodies: no headings or record
# syntax, so parsers see them as inert trailing prose inside the last section.
CRLF_PROBE = (b"Trailing CRLF probe line one.\r\n"
              b"Trailing CRLF probe line two.\r\n")


class ArtifactArchiveTest(V2CLITestCase):
    """CLI- and library-level tests for the verified export."""

    def setUp(self):
        super().setUp()
        self._out_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._out_tmp.cleanup)
        self.out_dir = self._out_tmp.name

    # -- helpers ------------------------------------------------------------

    def _prepare_reviewed(self, verdict="pass", total=1):
        """Drive the ticket to a recorded verdict with current bindings."""
        self.prepare_v2_review(total=total)
        self.write_review(verdict)
        proc = self.cli("set-review", self.TICKET, "--verdict", verdict)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def _export(self, name="artifacts.zip", output=None):
        out = output if output is not None else os.path.join(self.out_dir, name)
        proc = self.cli("archive-artifacts", self.TICKET, "--output", out)
        return proc, out

    def _read_zip(self, path):
        """Return (manifest_dict, {member_path: raw_bytes})."""
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            members = {n: zf.read(n) for n in names}
        self.assertIn("manifest.json", members)
        manifest = json.loads(members["manifest.json"].decode("utf-8"))
        return manifest, members

    def _assert_verified_zip(self, out):
        """Full manifest-vs-State verification of a produced archive."""
        manifest, members = self._read_zip(out)
        self.assertEqual(manifest["format_version"], 1)
        self.assertEqual(manifest["ticket_id"], self.TICKET)
        head = self._git("rev-parse", "HEAD").stdout.strip()
        self.assertEqual(manifest["snapshot_head"], head)

        entries = manifest["entries"]
        paths = [e["path"] for e in entries]
        self.assertEqual(paths, sorted(paths))  # entries sorted by path
        self.assertEqual(len(paths), len(set(paths)))
        by_path = {e["path"]: e for e in entries}

        # Every member's bytes hash to its manifest sha256.
        for entry in entries:
            member = members[entry["path"]]
            self.assertEqual(
                hashlib.sha256(member).hexdigest(), entry["sha256"])
            if entry["bound_sha256"] is None:
                self.assertNotIn("bound", entry)
            else:
                self.assertEqual(entry["sha256"], entry["bound_sha256"])

        data = self.read_state()
        evidence = data.get("evidence") or {}
        review = data.get("review") or {}
        plan_ref = (data.get("source_artifacts") or {}).get("plan") or {}

        # The manifest matches State exactly: every recorded binding appears
        # on the right member, supporting files carry null.
        self.assertEqual(
            by_path[".ai/work/T1/evidence.md"]["bound_sha256"],
            evidence.get("report_sha256"))
        self.assertEqual(
            by_path[".ai/work/T1/evidence-audit.md"]["bound_sha256"],
            evidence.get("audit_sha256"))
        self.assertEqual(
            by_path[".ai/work/T1/review.md"]["bound_sha256"],
            review.get("artifact_sha256"))
        self.assertEqual(
            by_path[plan_ref["path"].replace("\\", "/")]["bound_sha256"],
            review.get("plan_sha256"))
        for supporting in ("decision.md", "progress.md", "handoff.md"):
            self.assertIsNone(
                by_path[".ai/work/T1/%s" % supporting]["bound_sha256"])
        self.assertIsNone(by_path[".ai/work/T1/state.yaml"]["bound_sha256"])

        # The archived State bytes are the exact raw State bytes.
        self.assertEqual(members[".ai/work/T1/state.yaml"], self.state_bytes())
        # The Plan member sits at its registered source path.
        self.assertIn(plan_ref["path"].replace("\\", "/"), by_path)
        return manifest, members

    def _assert_rejected(self, proc, out, state_before=None):
        """Every rejection: exit 1, no partial output, State untouched."""
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertFalse(os.path.exists(out))
        if state_before is not None:
            self.assertEqual(self.state_bytes(), state_before)

    # -- index hints (HARDEN-010) ---------------------------------------------
    # Git pathspecs take forward slashes while file I/O needs the platform
    # separator, so hint targets are named repo-relative with `/`.

    def _set_flag(self, path, flag):
        """Set one or both index hints via separate Git commands.

        A single `update-index` cannot express the combination, so each bit is
        set on its own — the same reason the assessment clears them separately.
        """
        if flag in ("assume-unchanged", "both"):
            proc = self._git("update-index", "--assume-unchanged", path)
            self.assertEqual(proc.returncode, 0, proc.stderr)
        if flag in ("skip-worktree", "both"):
            proc = self._git("update-index", "--skip-worktree", path)
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def _clear_flag(self, path, flag):
        if flag in ("assume-unchanged", "both"):
            proc = self._git("update-index", "--no-assume-unchanged", path)
            self.assertEqual(proc.returncode, 0, proc.stderr)
        if flag in ("skip-worktree", "both"):
            proc = self._git("update-index", "--no-skip-worktree", path)
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def _flagged_edit(self, flag, rel):
        """Hint `rel`, then rewrite it at an unchanged byte size."""
        self._set_flag(rel, flag)
        full = os.path.join(self.root, rel)
        with open(full, "r", encoding="utf-8", newline="") as fh:
            original = fh.read()
        dirty = original.replace("return 42", "return 43")
        self.assertEqual(len(dirty), len(original))
        self.assertNotEqual(dirty, original)
        with open(full, "w", encoding="utf-8", newline="") as fh:
            fh.write(dirty)

    def _flagged_delete(self, flag, rel):
        self._set_flag(rel, flag)
        os.remove(os.path.join(self.root, rel))

    def _restore_code(self, rel):
        """Rewind `rel`'s worktree bytes from the index, keeping the binding.

        The reviewed HEAD predates `write_review`, so a `clean -fd`/`reset`
        rewind would delete the Review artifact and unbind the verdict; the
        mutated path is restored on its own instead. Hints must be cleared
        first, since `git checkout` skips a `skip-worktree` path.
        """
        proc = self._git("checkout", "--", rel)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    # -- success --------------------------------------------------------------

    def test_export_pass_review_produces_verified_zip(self):
        self._prepare_reviewed("pass")
        before_sources = self.capture_files()
        before_state = self.state_bytes()
        proc, out = self._export()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(os.path.exists(out))
        self._assert_verified_zip(out)
        # The export is read-only: repo snapshot and State bytes unchanged,
        # with the output kept outside the source snapshot.
        self.assertEqual(self.capture_files(), before_sources)
        self.assertEqual(self.state_bytes(), before_state)

    def test_export_changes_requested_current(self):
        # A current changes_requested verdict exports like a pass.
        self._prepare_reviewed("changes_requested")
        proc, out = self._export()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        manifest, members = self._assert_verified_zip(out)
        review_entry = next(e for e in manifest["entries"]
                            if e["path"].endswith("/review.md"))
        self.assertEqual(review_entry["sha256"], review_entry["bound_sha256"])

    def test_archive_fresh_clone_keeps_raw_bindings(self):
        """Mixed CRLF/LF originals survive fresh clone/export unchanged.

        Review Focus guard: work artifacts seeded with CRLF content folded
        into the LF template bytes must export with their raw digests, and
        the archive must still verify byte-exactly against its own manifest
        after the disposable repo is cloned to a second location.
        """
        self.seed_v2("evidence_audit")
        self.write_evidence(round_no=1)
        with open(os.path.join(self.work, "evidence.md"), "ab") as fh:
            fh.write(CRLF_PROBE)
        self.write_audit(gate="sufficient", round_no=1)
        proc = self.cli("set-gate", self.TICKET, "--gate", "sufficient",
                        "--round", "1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for target in ("technical_decision", "planning"):
            proc = self.cli("advance", self.TICKET, "--to", target)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        rel = self.write_plan(1)
        proc = self.cli("register-plan", self.TICKET, "--path", rel,
                        "--total", "1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = self.cli("advance", self.TICKET, "--to", "implementation")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.write_decision()
        with open(os.path.join(self.work, "decision.md"), "ab") as fh:
            fh.write(CRLF_PROBE)
        self.commit_code("src/feature.py", "def feature():\n    return 1\n")
        proc = self.cli("complete-task", self.TICKET, "--total", "1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.write_handoff()
        proc = self.cli("advance", self.TICKET, "--to", "review")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        head = self.commit_all("fixture: mixed-eol review tree")
        self.write_review("pass", reviewed_commit=head)
        # The whole Review is CRLF; line bodies stay identical to the LF
        # template, so `None` sections stay the explicit None text.
        review_path = os.path.join(self.work, "review.md")
        with open(review_path, "rb") as fh:
            lf_bytes = fh.read()
        with open(review_path, "wb") as fh:
            fh.write(lf_bytes.replace(b"\n", b"\r\n"))
        proc = self.cli("set-review", self.TICKET, "--verdict", "pass")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        proc, out = self._export()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        clone_dir = os.path.join(self.out_dir, "clone")
        cloned = subprocess.run(
            ["git", "clone", "-q", self.root, clone_dir],
            capture_output=True, text=True, env=self._env())
        self.assertEqual(cloned.returncode, 0, cloned.stdout + cloned.stderr)
        clone_head = subprocess.run(
            ["git", "-C", clone_dir, "rev-parse", "HEAD"],
            capture_output=True, text=True, env=self._env()).stdout.strip()
        self.assertEqual(head, clone_head)
        # Verify the archive from within the clone: the ZIP is self-contained
        # raw bytes and needs nothing from the originating worktree.
        shipped = os.path.join(clone_dir, "artifacts.zip")
        shutil.copyfile(out, shipped)
        manifest, members = self._read_zip(shipped)
        self.assertEqual(manifest["format_version"], 1)
        self.assertEqual(manifest["snapshot_head"], clone_head)
        for entry in manifest["entries"]:
            member = members[entry["path"]]
            digest = hashlib.sha256(member).hexdigest()
            self.assertEqual(digest, entry["sha256"])
            if entry["bound_sha256"] is not None:
                self.assertEqual(entry["sha256"], entry["bound_sha256"])
        # The mixed-CRLF/LF bytes survive byte-exactly in the members.
        self.assertIn(CRLF_PROBE, members[".ai/work/T1/evidence.md"])
        self.assertIn(CRLF_PROBE, members[".ai/work/T1/decision.md"])
        review_bytes = members[".ai/work/T1/review.md"]
        self.assertEqual(review_bytes.count(b"\n"),
                         review_bytes.count(b"\r\n"))
        self.assertIn(b"verdict: pass\r\n", review_bytes)

    # -- rejections (rc 1, no partial output) ----------------------------------

    def test_reject_pending_review(self):
        self.prepare_v2_review()
        before = self.state_bytes()
        proc, out = self._export()
        self._assert_rejected(proc, out, before)

    def test_reject_v1_ticket(self):
        self.seed_v1("review")
        before = self.state_bytes()
        proc, out = self._export()
        self._assert_rejected(proc, out, before)

    def test_reject_stale_review_artifact(self):
        self._prepare_reviewed("pass")
        review_path = os.path.join(self.work, "review.md")
        with open(review_path, "a", encoding="utf-8", newline="") as fh:
            fh.write("\nappended after the verdict\n")
        before = self.state_bytes()
        proc, out = self._export()
        self._assert_rejected(proc, out, before)

    def test_reject_stale_review_code(self):
        self._prepare_reviewed("pass")
        with open(os.path.join(self.root, "src", "app.py"), "a",
                  encoding="utf-8", newline="") as fh:
            fh.write("\nDRIFT = True\n")
        before = self.state_bytes()
        proc, out = self._export()
        self._assert_rejected(proc, out, before)

    def test_flagged_drift_leaves_no_archive(self):
        """A hint-hidden change refuses export and leaves no archive behind.

        `archive-artifacts` re-verifies against the same shared assessment, so an
        equal-size edit or a deletion under `assume-unchanged`/`skip-worktree`
        must refuse the export outright. Two things are pinned beyond the
        existing stale-code rejection: the refusal leaves nothing at all in the
        output directory (not just not the requested name, so no partial or temp
        archive survives), and the refused export still cannot touch the real
        index, its hint flags, or the recorded verdict.

        The same fixture exports while nothing is hidden, so the refusal is
        attributable to the hint rather than to an already-stale binding.
        """
        rel = "src/app.py"
        self._prepare_reviewed("pass")
        baseline_proc, baseline_out = self._export(name="baseline.zip")
        self.assertEqual(baseline_proc.returncode, 0,
                         baseline_proc.stdout + baseline_proc.stderr)
        self.assertTrue(os.path.exists(baseline_out))

        for flag in ("assume-unchanged", "skip-worktree", "both"):
            for kind in ("edit", "delete"):
                with self.subTest(flag=flag, kind=kind):
                    case_dir = os.path.join(self.out_dir, "case-%s-%s"
                                            % (flag, kind))
                    os.makedirs(case_dir)
                    if kind == "edit":
                        self._flagged_edit(flag, rel)
                    else:
                        self._flagged_delete(flag, rel)

                    index = os.path.join(self.root, ".git", "index")
                    before_state = self.state_bytes()
                    with open(index, "rb") as fh:
                        before_index = fh.read()
                    before_mtime = os.stat(index).st_mtime_ns
                    before_flags = self._git(
                        "ls-files", "-v", "-z", "--", rel).stdout

                    proc, out = self._export(
                        output=os.path.join(case_dir, "artifacts.zip"))
                    self._assert_rejected(proc, out, before_state)
                    self.assertEqual(os.listdir(case_dir), [],
                                     "refused export left output behind: %r"
                                     % os.listdir(case_dir))
                    self.assertEqual(
                        self.read_state()["review"]["verdict"], "pass")
                    with open(index, "rb") as fh:
                        self.assertEqual(fh.read(), before_index,
                                         ".git/index bytes changed")
                    self.assertEqual(os.stat(index).st_mtime_ns, before_mtime,
                                     ".git/index mtime changed")
                    self.assertEqual(
                        self._git("ls-files", "-v", "-z", "--", rel).stdout,
                        before_flags,
                        "index hints changed: the probe cleared the real index")

                    self._clear_flag(rel, flag)
                    self._restore_code(rel)

    def test_reject_stale_gate_binding(self):
        # The Review bindings stay intact; only the recorded Evidence hash no
        # longer matches the collected bytes, so the gate is stale. state.yaml
        # is review-exempt, so this isolates the gate-binding check.
        self._prepare_reviewed("pass")
        data = self.read_state()
        data["evidence"]["report_sha256"] = "0" * 64
        self.write_state(data)
        before = self.state_bytes()
        proc, out = self._export()
        self._assert_rejected(proc, out, before)

    def test_reject_rework_needing_new_review(self):
        # The repair path allows a strictly-appending rework Plan under a
        # changes_requested verdict; export does NOT inherit that exception.
        self._prepare_reviewed("changes_requested")
        plan_rel = self.write_plan(2)  # appends Task 2, Task 1 contract kept
        proc = self.cli("register-plan", self.TICKET, "--path", plan_rel,
                        "--total", "2")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        before = self.state_bytes()
        proc, out = self._export()
        self._assert_rejected(proc, out, before)

    def test_reject_unsafe_member_symlink_outside_root(self):
        self._prepare_reviewed("pass")
        outside = os.path.join(self.out_dir, "outside.md")
        with open(outside, "w", encoding="utf-8", newline="") as fh:
            fh.write("outside the repository\n")
        os.remove(os.path.join(self.work, "evidence.md"))
        try:
            os.symlink(outside, os.path.join(self.work, "evidence.md"))
        except OSError:
            self.skipTest("symlinks are not available in this environment")
        before = self.state_bytes()
        proc, out = self._export()
        self._assert_rejected(proc, out, before)

    def test_reject_output_colliding_with_input(self):
        self._prepare_reviewed("pass")
        state_path = os.path.join(self.work, "state.yaml")
        before_state_bytes = self.state_bytes()
        proc, out = self._export(output=state_path)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        # The collided input keeps its exact bytes.
        self.assertEqual(self.state_bytes(), before_state_bytes)

    def test_reject_pre_existing_output_keeps_bytes(self):
        self._prepare_reviewed("pass")
        out = os.path.join(self.out_dir, "artifacts.zip")
        with open(out, "wb") as fh:
            fh.write(b"KEEP-ME")
        proc, _ = self._export()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        with open(out, "rb") as fh:
            self.assertEqual(fh.read(), b"KEEP-ME")

    def test_injected_write_failure_leaves_no_partial_archive(self):
        self._prepare_reviewed("pass")
        out = os.path.join(self.out_dir, "artifacts.zip")
        real_writestr = zipfile.ZipFile.writestr
        state = {"calls": 0}

        def flaky_writestr(zf, *args, **kwargs):
            state["calls"] += 1
            if state["calls"] >= 2:  # fail after the manifest member
                raise OSError("injected write failure")
            return real_writestr(zf, *args, **kwargs)

        before = self.state_bytes()
        with mock.patch.object(zipfile.ZipFile, "writestr", flaky_writestr):
            with self.assertRaises(artifact_archive.ArchiveError):
                artifact_archive.archive_ticket(self.root, self.TICKET, out)
        self.assertFalse(os.path.exists(out))
        self.assertEqual(os.listdir(self.out_dir), [])  # no temp leftovers
        self.assertEqual(self.state_bytes(), before)

    # -- write_archive unit behavior --------------------------------------------

    def test_write_archive_success_roundtrip(self):
        out = os.path.join(self.out_dir, "unit.zip")
        entries = {
            "b-second.md": b"second\n",
            "a-first.md": b"first\n",
            "dir/nested.md": b"nested\n",
        }
        bindings = {"a-first.md": hashlib.sha256(b"first\n").hexdigest()}
        dest = artifact_archive.write_archive(
            out, ticket_id="T-UNIT", snapshot_head="a" * 40,
            entries=entries, bindings=bindings)
        self.assertEqual(os.path.abspath(dest), os.path.abspath(out))
        manifest, members = self._read_zip(out)
        self.assertEqual([e["path"] for e in manifest["entries"]],
                         ["a-first.md", "b-second.md", "dir/nested.md"])
        self.assertEqual(members["a-first.md"], b"first\n")
        self.assertEqual(members["dir/nested.md"], b"nested\n")
        self.assertEqual(manifest["ticket_id"], "T-UNIT")
        self.assertEqual(manifest["snapshot_head"], "a" * 40)
        bound = {e["path"]: e["bound_sha256"]
                 for e in manifest["entries"]}
        self.assertEqual(bound["a-first.md"],
                         hashlib.sha256(b"first\n").hexdigest())
        self.assertIsNone(bound["b-second.md"])
        self.assertIsNone(bound["dir/nested.md"])

    def test_write_archive_rejects_traversal(self):
        out = os.path.join(self.out_dir, "traversal.zip")
        for evil in ("../evil.md", "a/../../evil.md", "/absolute.md",
                     "C:/drive.md", "a\\..\\..\\evil.md"):
            with self.assertRaises(artifact_archive.ArchiveError):
                artifact_archive.write_archive(
                    out, ticket_id="T", snapshot_head="a" * 40,
                    entries={evil: b"x"}, bindings={})
            self.assertFalse(os.path.exists(out))

    def test_write_archive_rejects_duplicate_members(self):
        out = os.path.join(self.out_dir, "dup.zip")
        with self.assertRaises(artifact_archive.ArchiveError):
            artifact_archive.write_archive(
                out, ticket_id="T", snapshot_head="a" * 40,
                entries={"a/b.md": b"one", "a\\b.md": b"two"}, bindings={})
        self.assertFalse(os.path.exists(out))

    def test_write_archive_rejects_reserved_manifest_member(self):
        out = os.path.join(self.out_dir, "reserved.zip")
        with self.assertRaises(artifact_archive.ArchiveError):
            artifact_archive.write_archive(
                out, ticket_id="T", snapshot_head="a" * 40,
                entries={"manifest.json": b"fake"}, bindings={})
        self.assertFalse(os.path.exists(out))

    def test_write_archive_rejects_binding_mismatch(self):
        # A binding that does not match the member bytes must never be
        # published into a manifest.
        out = os.path.join(self.out_dir, "mismatch.zip")
        with self.assertRaises(artifact_archive.ArchiveError):
            artifact_archive.write_archive(
                out, ticket_id="T", snapshot_head="a" * 40,
                entries={"a.md": b"real bytes"},
                bindings={"a.md": "b" * 64})
        self.assertFalse(os.path.exists(out))

    # -- usage errors (exit 2) ---------------------------------------------------

    def test_usage_errors_exit_2(self):
        for args in (
            ("archive-artifacts",),  # no ticket
            ("archive-artifacts", self.TICKET),  # no --output
            ("archive-artifacts", self.TICKET, "--output"),  # missing value
            ("archive-artifacts", self.TICKET, "--bogus", "x"),
        ):
            proc = self.cli(*args)
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)

    def test_unknown_ticket_rejected(self):
        proc, out = self._export()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertFalse(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
