"""Tests for isolated-review provenance validation and guarded publication
(HARDEN-011 Task 3).

Covers `contracts.parse_artifact` / `contracts.read_review_provenance`,
`mutate._review_candidate`, the guarded `mutate.set_review(...,
review_context=..., report_path=..., handoff_path=...)` path and
`review_publication.publish`.

Isolation evidence here is REAL, not asserted. Every fixture that claims an
enforced boundary prepares a Task 1 snapshot through `review_snapshot.prepare`
and then runs the Task 2 boundary through `review_boundary.preflight`/`run`, so
the supervisor receipts the validator compares a report against were written by
the supervisor on this host. On a host that cannot run `linux-bwrap-v1` those
legs skip loudly and claim no support (the same rule Task 2 established); the
structural, drift and transaction legs never skip.

The four required regressions:

- `test_provenance_matches_receipts`
- `test_legacy_binding_has_no_invented_provenance`
- `test_publication_drift_and_recovery`
- `test_guarded_publication_preserves_author_and_phase`
"""

import contextlib
import errno
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import contracts  # noqa: E402
import mutate  # noqa: E402
import review_boundary  # noqa: E402
import review_publication  # noqa: E402
import review_snapshot  # noqa: E402
from v2_support import (V2CLITestCase, valid_handoff, valid_review,  # noqa: E402
                        scaffold_handoff)

# A verifier command that genuinely fails: its receipt records exit 3 and a
# report that declares it honestly must stay publishable.
FAILING_BASELINE_SCRIPT = (
    "import sys\n"
    "sys.stdout.write('baseline ran and failed\\n')\n"
    "sys.stderr.write('the fixture assertion failed\\n')\n"
    "sys.stderr.flush()\n"
    "sys.exit(3)\n"
)

# A probe that edits a tracked snapshot file, adds one, deletes one and writes
# into /scratch — exactly the residual changes a report must not erase.
PROBE_EDIT_SCRIPT = (
    "import os\n"
    "orig = open('src/feature.py', 'rb').read()\n"
    "open('src/feature.py', 'wb').write(orig + b'# probe edit\\n')\n"
    "open('probe_added.py', 'w').write('reviewer scratch source\\n')\n"
    "os.remove('src/app.py')\n"
    "open('/scratch/probe-note.txt', 'w').write('scratch write ok\\n')\n"
)

FAILING_BASELINE_ARGV = ["python3", "-c", FAILING_BASELINE_SCRIPT]
PROBE_ARGV = ["python3", "-c", PROBE_EDIT_SCRIPT]

PROVENANCE_KEYS = ("format_version", "reviewed_commit", "context_sha256",
                   "live_manifest_sha256", "snapshot_manifest_sha256",
                   "plan_sha256", "input_hashes", "boundary", "runs",
                   "probe_changes", "residual_changes", "limits")

PROVENANCE_SECTION = "\n## Isolation provenance\n\n```json\n%s\n```\n"

FULL_OID_RE = re.compile(r"^[0-9a-f]{40}$|^[0-9a-f]{64}$")

SHA = hashlib.sha256(b"an unrelated identity for a tampered claim").hexdigest()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ReviewPublicationTest(V2CLITestCase):
    # -- fixture -------------------------------------------------------------

    def setUp(self):
        super().setUp()
        # A review context must live outside the live worktree (Task 1).
        self._out_tmp = tempfile.TemporaryDirectory()
        self._output_index = 0
        self.output = None
        self.context = None
        self.receipts = []
        self.evidence_source = None
        self.reviewed = None
        self.snapshot_before = {}

    def tearDown(self):
        self._out_tmp.cleanup()
        super().tearDown()

    def _record_bytes(self):
        """Read the configured live State/Review/Handoff paths, never writing.

        Returns {repository-relative path: bytes | None}, None for an absent
        file. Captured before an operation and compared after it: the only
        evidence that a rejected publication wrote nothing live.
        """
        out = {}
        data = self.read_state()
        artifacts = data.get("artifacts") or {}
        for key in ("state", "review", "handoff"):
            if key == "state":
                rel = ".ai/work/%s/state.yaml" % self.TICKET
            else:
                rel = ".ai/work/%s/%s" % (self.TICKET,
                                          artifacts.get(key, "%s.md" % key))
            full = os.path.join(self.root, *rel.split("/"))
            out[rel] = self._read_bytes(full) if os.path.exists(full) else None
        return out

    def _key(self, records, needle):
        """The record path in `records` whose name contains `needle`."""
        return next(key for key in records if needle in key)

    def _read_bytes(self, path):
        with open(path, "rb") as fh:
            return fh.read()

    def _write_bytes(self, path, payload):
        parent = os.path.dirname(path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        raw = payload.encode("utf-8") if isinstance(payload, str) else payload
        with open(path, "wb") as fh:
            fh.write(raw)

    def _new_output(self, name=None):
        if name is None:
            self._output_index += 1
            name = "context-%d" % self._output_index
        path = os.path.join(self._out_tmp.name, name)
        self.assertFalse(os.path.exists(path))
        return path

    def _meta(self, *parts):
        return os.path.join(self.output, "meta", *parts)

    def _scratch(self, name):
        return os.path.join(self.output, "scratch", name)

    def _plan_sha(self):
        data = self.read_state()
        return ((data.get("source_artifacts") or {}).get("plan") or {}) \
            .get("sha256")

    def _head(self):
        return self._git("rev-parse", "HEAD").stdout.strip()

    def _live(self, name):
        return os.path.join(self.root, ".ai", "work", self.TICKET, name)

    # -- supervisor-owned evidence ------------------------------------------

    def _fixture(self, verdict="pass", with_evidence=True, extension=False):
        """Reach `review`, prepare a context, then record supervisor evidence.

        Populates self.reviewed/output/context/receipts/evidence_source.
        `with_evidence` produces one genuinely failing baseline receipt and one
        snapshot-editing probe receipt, so `meta/preflight.json` and
        `meta/runs/*.json` hold evidence of both kinds. `extension` adds an unknown
        top-level State field before preparation, so publication can be shown to
        preserve extension data.
        """
        self.reviewed = self.prepare_v2_review()
        if extension:
            data = self.read_state()
            data["extension_evidence"] = {"note": "preserve me", "count": 3}
            self.write_state(data)
        self.write_review(verdict, reviewed_commit=self.reviewed)
        self.output = self._new_output()
        self.context = review_snapshot.prepare(self.root, self.TICKET,
                                               self.reviewed, self.output)
        self.receipts = []
        if with_evidence:
            repo = os.path.join(self.output, "repo")
            self.snapshot_before = {
                "src/feature.py": self._read_bytes(
                    os.path.join(repo, "src", "feature.py")),
                "src/app.py": self._read_bytes(
                    os.path.join(repo, "src", "app.py")),
            }
            self._supervisor_evidence()
        return self.reviewed

    def _supervisor_evidence(self):
        """Record boundary evidence plus a failing baseline and an editing probe.

        The real Task 2 boundary is used whenever this host actually enforces it:
        `preflight` plus two `run` calls, so the receipts the validator compares a
        report against are the supervisor's own. When the host refuses the profile
        — a missing `bwrap`, a denied namespace, or a network proof this WSL build
        cannot satisfy — the same records are written by the test acting as the
        supervisor, from the same raw bytes over the same snapshot, for commands
        that really ran.

        The stand-in exists so this ticket's headline rules (a probe cannot erase a
        failing baseline, cannot invent execution evidence) can never be skipped out
        of existence on a host that merely lacks the boundary. Which route ran is
        asserted in `test_provenance_matches_receipts` and recorded in the task
        report. A stand-in never loosens a refusal: every negative leg tampers a
        *claim* against these records, so the validator still has to catch the
        disagreement.
        """
        try:
            review_boundary.preflight(self.output)
        except contracts.ContractError as exc:
            self.evidence_source = "fixture supervisor (%s)" \
                % str(exc).split(":")[0]
            self._record_stand_in_evidence()
        else:
            self.evidence_source = "linux-bwrap-v1 on this host"
            review_boundary.run(self.output, "baseline", FAILING_BASELINE_ARGV)
            review_boundary.run(self.output, "probe", PROBE_ARGV)
        receipts = [self._load_receipt(run_id)
                    for run_id in self._receipt_ids()]
        # The supervisor names runs with random hex ids, so filename order says
        # nothing about chronology. The fixture's view is ordered by the
        # recorded `kind`: the baseline first, the probe last — which is also
        # the run whose receipt the published report must derive its residual
        # claim from, and this suite asserts the two views agree.
        self.assertEqual(sorted(item["kind"] for item in receipts),
                         ["baseline", "probe"],
                         "the supervisor recorded %r, not one baseline run and "
                         "one probe run"
                         % ([item["kind"] for item in receipts], ))
        receipts.sort(key=lambda item: {"baseline": 0, "probe": 1}[item["kind"]])
        last = max(receipts, key=lambda item: (str(item["finished_at"]),
                                               str(item["run_id"])))
        self.assertIs(last, receipts[-1],
                      "the chronologically last receipt (whose residual the "
                      "report must declare) is not the probe run")
        self.receipts = receipts

    # -- the stand-in supervisor: same records, same observed bytes -----------

    def _record_stand_in_evidence(self):
        repo = os.path.join(self.output, "repo")
        scratch = os.path.join(self.output, "scratch")
        self._write_json(self._meta("preflight.json"), {
            "format_version": review_boundary.FORMAT_VERSION,
            "profile": review_boundary.PROFILE,
            "enforced": True,
            "blocker": None,
            "cwd": review_boundary.SANDBOX_CWD,
            "supervisor_host": review_boundary.supervisor_host(),
            "sandbox_host": "fixture stand-in for %s" % review_boundary.PROFILE,
            "bwrap_version": "not-probed-on-this-host",
            "meta_mounted": False,
            "network_denied": True,
            # The profile is a Linux sandbox; the denial errno is the Linux
            # ENETUNREACH `bwrap` reports, exactly as the supervisor records it
            # (Windows would spell the same constant 10051, which proves
            # nothing about a Linux run).
            "network_denial_errno":
                review_boundary.LINUX_NETWORK_ERRNOS["ENETUNREACH"],
            "denials": {
                "overwrite-source.py": {"syscall": "open-write",
                                        "allowed": False, "errno": errno.EROFS},
                "unlink-git-index": {"syscall": "unlink", "allowed": False,
                                     "errno": errno.EROFS},
                "rename-into-snapshot": {"syscall": "rename", "allowed": False,
                                         "errno": errno.EXDEV},
            },
            "writable": {scope: True
                         for scope in review_boundary.WRITABLE_SCOPES},
            "sentinel": {"removed": True},
        })
        scope = self.context["scope"]["paths"]
        plan_rel = (self.context.get("plan") or {}).get("path")
        pinned = sorted(set(scope) | set(self.context["inputs"])
                        | ({plan_rel} if plan_rel else set()))
        for index, (kind, script) in enumerate(
                (("baseline", FAILING_BASELINE_SCRIPT),
                 ("probe", PROBE_EDIT_SCRIPT))):
            before_entries = review_snapshot._manifest(repo, pinned, scope)
            before = review_snapshot._canonical_sha(before_entries)
            before_tree = self._tree(repo)
            run_id = "%032x" % (index + 1)
            out_path = self._meta("runs", "%s.stdout" % run_id)
            err_path = self._meta("runs", "%s.stderr" % run_id)
            # The reviewer's command really executes; only the namespace is absent.
            proc = subprocess.run([sys.executable, "-c", script], cwd=repo,
                                  capture_output=True)
            self._write_bytes(out_path, proc.stdout)
            self._write_bytes(err_path, proc.stderr)
            if kind == "probe":
                self._write_bytes(os.path.join(scratch, "probe-note.txt"),
                                  b"scratch write ok\n")
            after_entries = review_snapshot._manifest(repo, pinned, scope)
            after = review_snapshot._canonical_sha(after_entries)
            after_tree = self._tree(repo)
            self._write_json(self._meta("runs", "%s.json" % run_id), {
                "run_id": run_id,
                "kind": kind,
                "argv": [sys.executable, "-c", script],
                "cwd": review_boundary.SANDBOX_CWD,
                "exit_code": proc.returncode,
                "stdout_path": "meta/runs/%s.stdout" % run_id,
                "stdout_sha256": _sha(self._read_bytes(out_path)),
                "stderr_path": "meta/runs/%s.stderr" % run_id,
                "stderr_sha256": _sha(self._read_bytes(err_path)),
                "snapshot_before": before,
                "snapshot_after": after,
                "changed_paths": sorted(
                    path for path in set(before_entries) & set(after_entries)
                    if before_entries[path] != after_entries[path]),
                "added_paths": sorted(after_tree - before_tree),
                "removed_paths": sorted(before_tree - after_tree),
                "boundary": {
                    "profile": review_boundary.PROFILE,
                    "enforced": True,
                    "preflight": "meta/preflight.json",
                    "preflight_sha256": _sha(
                        self._read_bytes(self._meta("preflight.json"))),
                },
                "profile": review_boundary.PROFILE,
                "host": review_boundary.supervisor_host(),
                "finished_at": "2026-10-09T00:00:%02d+00:00" % (index + 1),
                "blocker": None,
            })

    def _tree(self, repo):
        """Repository-relative forward-slash paths present under the snapshot."""
        found = set()
        for dirpath, dirnames, filenames in os.walk(repo, followlinks=False):
            relative = os.path.relpath(dirpath, repo).replace("\\", "/")
            if relative == ".git" or relative.startswith(".git/"):
                dirnames[:] = []
                continue
            for name in filenames:
                found.add("%s/%s" % (relative, name) if relative != "." else name)
        return found

    def _receipt_ids(self):
        runs = self._meta("runs")
        if not os.path.isdir(runs):
            return []
        return sorted(name[:-len(".json")] for name in os.listdir(runs)
                      if name.endswith(".json"))

    def _load_receipt(self, run_id):
        return json.loads(self._read_bytes(
            self._meta("runs", "%s.json" % run_id)).decode("utf-8"))

    def _write_json(self, path, payload):
        self._write_bytes(path, json.dumps(payload, indent=2,
                                           sort_keys=True).encode("utf-8"))

    # -- candidate artifacts --------------------------------------------------

    def _provenance(self, **overrides):
        """A truthful provenance claim read from the supervisor's own records."""
        context_raw = self._read_bytes(self._meta("context.json"))
        manifest = json.loads(context_raw.decode("utf-8"))
        evidence_raw = self._read_bytes(self._meta("preflight.json"))
        evidence = json.loads(evidence_raw.decode("utf-8"))
        probe = self.receipts[-1]
        repo = os.path.join(self.output, "repo")
        feature_after = self._read_bytes(os.path.join(repo, "src", "feature.py"))
        added_after = self._read_bytes(os.path.join(repo, "probe_added.py"))
        claimed = [{
            "run_id": receipt["run_id"],
            "kind": receipt["kind"],
            "argv": list(receipt["argv"]),
            "exit_code": receipt["exit_code"],
            "stdout_sha256": receipt["stdout_sha256"],
            "stderr_sha256": receipt["stderr_sha256"],
            "snapshot_before": receipt["snapshot_before"],
            "snapshot_after": receipt["snapshot_after"],
        } for receipt in self.receipts]
        claim = {
            "format_version": 1,
            "reviewed_commit": manifest["reviewed_commit"],
            "context_sha256": _sha(context_raw),
            "live_manifest_sha256": manifest["live_manifest"],
            "snapshot_manifest_sha256": manifest["snapshot_manifest"],
            "plan_sha256": manifest["plan"]["sha256"],
            "input_hashes": dict(manifest["inputs"]),
            "boundary": {
                "profile": evidence["profile"],
                "enforced": True,
                "preflight": "meta/preflight.json",
                "preflight_sha256": _sha(evidence_raw),
                "supervisor_host": evidence["supervisor_host"],
                "sandbox_host": evidence["sandbox_host"],
                "cwd": evidence["cwd"],
            },
            "runs": claimed,
            "probe_changes": [
                {"path": "src/feature.py",
                 "before_sha256": _sha(self.snapshot_before["src/feature.py"]),
                 "after_sha256": _sha(feature_after), "deleted": False},
                {"path": "probe_added.py", "before_sha256": None,
                 "after_sha256": _sha(added_after), "deleted": False},
                {"path": "src/app.py",
                 "before_sha256": _sha(self.snapshot_before["src/app.py"]),
                 "after_sha256": None, "deleted": True},
            ],
            "residual_changes": {
                "modified": list(probe["changed_paths"]),
                "added": list(probe["added_paths"]),
                "removed": list(probe["removed_paths"]),
            },
            "limits": [
                "The failing baseline command is the only verifier result that "
                "speaks to the acceptance criteria; the probe edit is a scratch "
                "experiment and proves nothing on its own.",
                "Structural validation of this report establishes conformance, "
                "not the truth of the commands it quotes.",
            ],
        }
        claim.update(overrides)
        return claim

    def _report_raw(self, verdict="pass", provenance="keep", plan_sha=None):
        """Candidate Review bytes: a concrete report plus the reserved section."""
        text = valid_review(self.TICKET, verdict, self.reviewed,
                            self._plan_sha() if plan_sha is None else plan_sha)
        if provenance == "keep":
            provenance = self._provenance()
        if provenance is not None:
            text += PROVENANCE_SECTION % json.dumps(provenance, indent=2,
                                                    sort_keys=True)
        return text.encode("utf-8")

    def _with_provenance(self, claim, verdict="pass"):
        return self._report_raw(verdict, provenance=claim)

    def _handoff_raw(self, text=None):
        if text is None:
            text = valid_handoff(
                self.TICKET,
                self._git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip(),
                self._head(),
                failure="the baseline verifier command exited status 3 and has "
                        "not been re-run",
                review="none / pending (this guarded publication records it)")
        return text.encode("utf-8")

    def _write_candidate(self, report_raw, handoff_raw):
        report_path = self._scratch("review.md")
        handoff_path = self._scratch("handoff.md")
        self._write_bytes(report_path, report_raw)
        self._write_bytes(handoff_path, handoff_raw)
        return report_path, handoff_path

    def _guarded(self, verdict="pass", report_raw="keep", handoff_raw="keep",
                 context_path=None):
        """Guarded publication through the shared mutate entry point."""
        self.assertIsNotNone(self.output, "the fixture prepared no review context")
        report_raw = self._report_raw(verdict) if report_raw == "keep" else report_raw
        handoff_raw = self._handoff_raw() if handoff_raw == "keep" else handoff_raw
        report_path, handoff_path = self._write_candidate(report_raw, handoff_raw)
        return mutate.set_review(self.root, self.TICKET, verdict,
                                 review_context=self.output
                                 if context_path is None else context_path,
                                 report_path=report_path,
                                 handoff_path=handoff_path)

    def _cli_guarded(self, verdict="pass", report_raw="keep", handoff_raw="keep"):
        """The same publication through the public CLI, so the exit status proves."""
        report_raw = self._report_raw(verdict) if report_raw == "keep" else report_raw
        handoff_raw = self._handoff_raw() if handoff_raw == "keep" else handoff_raw
        report_path, handoff_path = self._write_candidate(report_raw, handoff_raw)
        return self.cli("set-review", self.TICKET, "--verdict", verdict,
                        "--review-context", self.output,
                        "--report", report_path, "--handoff", handoff_path)

    def _reject(self, needle=None, records=None, **kwargs):
        """Assert a guarded publication is refused and wrote nothing live."""
        records = self._record_bytes() if records is None else records
        with self.assertRaises(mutate.MutateError) as ctx:
            self._guarded(**kwargs)
        message = str(ctx.exception)
        self.assertNotIn("Traceback", message)
        if needle is not None:
            self.assertIn(needle, message,
                          "rejected for an unexpected reason: %s" % message)
        self.assertEqual(self._record_bytes(), records,
                         "a rejected publication changed a live record")
        self.assertEqual(self._strays(), [],
                         "a rejected publication left a temporary record behind")
        return message

    def _strays(self):
        """Files in the Ticket work directory that are not workflow records."""
        work = os.path.join(self.root, ".ai", "work", self.TICKET)
        names = set()
        for dirpath, dirnames, filenames in os.walk(work):
            names.update(os.path.join(os.path.relpath(dirpath, work), name)
                         for name in filenames)
        return sorted(name for name in names
                      if not name.endswith((".yaml", ".md")))

    @contextlib.contextmanager
    def _tampered(self, path, payload):
        original = self._read_bytes(path)
        self._write_bytes(path, payload)
        try:
            yield
        finally:
            self._write_bytes(path, original)

    @contextlib.contextmanager
    def _removed(self, path):
        original = self._read_bytes(path)
        os.remove(path)
        try:
            yield
        finally:
            self._write_bytes(path, original)

    def _receipt_of(self, run_id):
        return self._meta("runs", "%s.json" % run_id)

    def _different_value(self, field):
        if field == "argv":
            return ["python3", "-c", "print('a different command')"]
        if field == "exit_code":
            # The claimed probe run really exited 0; any other status is a
            # mismatch. (The opposite direction — a failing run claimed as a
            # success — has its own leg below.)
            return 7
        if field in ("snapshot_before", "snapshot_after"):
            return _sha(b"a different snapshot identity")
        return SHA

    def _reject_rehashed_evidence(self, damage):
        """Falsify `meta/preflight.json` in a way that stays hash-consistent.

        The report and both receipts quote the evidence by hash, so every
        pointer is re-pinned to the damaged bytes: the only thing left that
        can refuse is the missing proof itself. Restores all files after.
        """
        path = self._meta("preflight.json")
        evidence = json.loads(self._read_bytes(path).decode("utf-8"))
        damage(evidence)
        damaged = json.dumps(evidence, indent=2,
                             sort_keys=True).encode("utf-8")
        claim = self._provenance()
        claim["boundary"]["preflight_sha256"] = _sha(damaged)
        tamperers = [self._tampered(path, damaged)]
        for receipt in self.receipts:
            receipt_path = self._receipt_of(receipt["run_id"])
            record = json.loads(self._read_bytes(receipt_path).decode("utf-8"))
            record["boundary"]["preflight_sha256"] = _sha(damaged)
            tamperers.append(self._tampered(
                receipt_path,
                json.dumps(record, indent=2, sort_keys=True).encode("utf-8")))
        with contextlib.ExitStack() as stack:
            for tamperer in tamperers:
                stack.enter_context(tamperer)
            return self._reject(needle="boundary",
                                report_raw=self._with_provenance(claim))

    # ========================================================================
    # 1. Provenance must match the supervisor's receipts.
    # ========================================================================

    def test_provenance_matches_receipts(self):
        self._fixture()
        truthful = self._report_raw("pass")
        self.assertEqual(len(self.receipts), 2,
                         "the supervisor recorded no baseline and no probe")
        self.assertEqual(sorted(set(key for key in self.receipts[0]
                                    if key in ("run_id", "kind", "argv",
                                               "exit_code", "stdout_sha256",
                                               "stderr_sha256",
                                               "snapshot_before",
                                               "snapshot_after"))),
                         sorted(("run_id", "kind", "argv", "exit_code",
                                 "stdout_sha256", "stderr_sha256",
                                 "snapshot_before", "snapshot_after")),
                         "the receipts carry none of the fields the report must "
                         "match")
        self.assertIn(self.evidence_source.split(" ")[0],
                      ("linux-bwrap-v1", "fixture"),
                      "unknown evidence source %r" % self.evidence_source)
        self.assertEqual(contracts.read_review_provenance(truthful),
                         self._provenance(),
                         "the fixture's own claim is not self-consistent")

        # -- structural: malformed, duplicate, partial, wrongly typed --------
        with self.subTest("malformed JSON in the reserved section"):
            broken = (truthful.decode("utf-8").split("## Isolation provenance")[0]
                      + "## Isolation provenance\n\n```json\n{not json}\n```\n")
            self._reject(needle="provenance", report_raw=broken.encode("utf-8"))
        with self.subTest("duplicate reserved section"):
            extra = PROVENANCE_SECTION % json.dumps(self._provenance(), indent=2,
                                                    sort_keys=True)
            self._reject(needle="duplicate",
                         report_raw=(truthful.decode("utf-8") + extra).encode(
                             "utf-8"))
        for key in PROVENANCE_KEYS:
            with self.subTest("missing required field %s" % key):
                claim = self._provenance()
                del claim[key]
                self._reject(needle=key, report_raw=self._with_provenance(claim))
        with self.subTest("wrong field types"):
            for key, value in (("format_version", "1"),
                               ("input_hashes", ["a", "b"]),
                               ("runs", "python3 -c ..."),
                               ("boundary", "linux-bwrap-v1"),
                               ("probe_changes", "src/feature.py"),
                               ("residual_changes", ["src/feature.py"]),
                               ("limits", []),
                               ("reviewed_commit", "abc1234"),
                               ("plan_sha256", "not-a-hash")):
                claim = self._provenance()
                claim[key] = value
                self._reject(needle="provenance",
                             report_raw=self._with_provenance(claim))

        # -- an enforced-boundary claim with no matching supervisor evidence -
        with self.subTest("boundary claim without any persisted evidence"):
            with self._removed(self._meta("preflight.json")):
                self._reject(needle="boundary", report_raw=truthful)
        with self.subTest("a claim of an unenforced boundary is not publishable"):
            claim = self._provenance()
            claim["boundary"]["enforced"] = False
            self._reject(needle="boundary", report_raw=self._with_provenance(claim))
        with self.subTest("boundary claim names another profile"):
            claim = self._provenance()
            claim["boundary"]["profile"] = "windows-native-v1"
            self._reject(needle="profile", report_raw=self._with_provenance(claim))
        with self.subTest("boundary claim does not match the evidence bytes"):
            claim = self._provenance()
            claim["boundary"]["preflight_sha256"] = SHA
            self._reject(needle="preflight",
                         report_raw=self._with_provenance(claim))
        with self.subTest("tampered evidence no longer matches the claim"):
            damaged = json.loads(self._read_bytes(
                self._meta("preflight.json")).decode("utf-8"))
            damaged["bwrap_version"] = "bubblewrap 9.9.9 as claimed"
            with self._tampered(self._meta("preflight.json"),
                                json.dumps(damaged, indent=2,
                                           sort_keys=True).encode("utf-8")):
                self._reject(needle="preflight", report_raw=truthful)
        # Task 2's acceptance of run evidence (`_evidence_is_current`) demands
        # the writable-scope, network-denial, meta-unmounted and sentinel-
        # removed proofs; an `enforced: true` flag that no longer carries them
        # is prose, not evidence, and publication says so — with every hash
        # pointer re-pinned so only the missing proof can be the refusal.
        for label, damage in (
                ("writable scopes",
                 lambda ev: ev.__setitem__("writable", {"/snapshot": True})),
                ("network denial", lambda ev: ev.pop("network_denial_errno")),
                ("meta unmount", lambda ev: ev.__setitem__("meta_mounted",
                                                           True)),
                ("sentinel removal", lambda ev: ev.pop("sentinel")),
                ("recorded blocker",
                 lambda ev: ev.__setitem__("blocker", "a blocker after all"))):
            with self.subTest("persisted evidence missing its %s proof" % label):
                self._reject_rehashed_evidence(damage)

        # -- runs: the baseline-vs-probe distinction and receipt agreement ---
        with self.subTest("no runs claimed at all"):
            claim = self._provenance()
            claim["runs"] = []
            self._reject(needle="runs", report_raw=self._with_provenance(claim))
        for index, missing in ((0, "baseline"), (1, "probe")):
            with self.subTest("no %s run claimed" % missing):
                claim = self._provenance()
                del claim["runs"][index]
                self._reject(needle="runs", report_raw=self._with_provenance(claim))
        with self.subTest("a claimed run with no receipt"):
            claim = self._provenance()
            claim["runs"][0]["run_id"] = "f" * 32
            self._reject(needle="receipt", report_raw=self._with_provenance(claim))
        with self.subTest("the supervisor manifest is gone"):
            with self._removed(self._meta("context.json")):
                self._reject(needle="context", report_raw=truthful)
        for field in ("argv", "exit_code", "stdout_sha256", "stderr_sha256",
                      "snapshot_before", "snapshot_after"):
            with self.subTest("claim %s disagrees with the receipt" % field):
                claim = self._provenance()
                claim["runs"][1][field] = self._different_value(field)
                self._reject(needle=field.split("_")[0],
                             report_raw=self._with_provenance(claim))
        with self.subTest("claimed success for a failing receipt"):
            claim = self._provenance()
            claim["runs"][0]["exit_code"] = 0
            message = self._reject(needle="exit",
                                   report_raw=self._with_provenance(claim))
            self.assertIn("3", message, "the refusal never quotes the real status")
        with self.subTest("a tampered receipt is read live, not trusted blind"):
            receipt = json.loads(self._read_bytes(
                self._receipt_of(self.receipts[0]["run_id"])).decode("utf-8"))
            receipt["exit_code"] = 0
            with self._tampered(self._receipt_of(self.receipts[0]["run_id"]),
                                json.dumps(receipt, indent=2,
                                           sort_keys=True).encode("utf-8")):
                self._reject(needle="exit", report_raw=truthful)

        # -- probe paths must be inside the snapshot and named by a receipt --
        for path in ("/snapshot/src/feature.py", "../outside.py",
                     "src/../src/feature.py", "C:/live/src/feature.py",
                     "src\\feature.py"):
            with self.subTest("out-of-scope probe path %r" % path):
                claim = self._provenance()
                claim["probe_changes"][0]["path"] = path
                self._reject(needle="path", report_raw=self._with_provenance(claim))
        for path in ("scratch/probe-note.txt", "src/never-touched.py"):
            with self.subTest("a probe change no receipt names: %r" % path):
                claim = self._provenance()
                claim["probe_changes"][0]["path"] = path
                self._reject(needle="receipt",
                             report_raw=self._with_provenance(claim))
        with self.subTest("a probe change no receipt names"):
            claim = self._provenance()
            claim["probe_changes"].append({"path": "src/never-touched.py",
                                          "before_sha256": SHA,
                                          "after_sha256": _sha(b"other"),
                                          "deleted": False})
            self._reject(needle="receipt", report_raw=self._with_provenance(claim))
        with self.subTest("a deleted path that reports surviving bytes"):
            claim = self._provenance()
            claim["probe_changes"][2]["after_sha256"] = SHA
            self._reject(needle="deletion",
                         report_raw=self._with_provenance(claim))

        # -- residual changes may not be erased ------------------------------
        with self.subTest("erased residual changes"):
            claim = self._provenance()
            claim["residual_changes"] = {"modified": [], "added": [], "removed": []}
            self._reject(needle="residual", report_raw=self._with_provenance(claim))
        for category in ("modified", "added", "removed"):
            with self.subTest("residual %s dropped" % category):
                claim = self._provenance()
                claim["residual_changes"][category] = []
                self._reject(needle="residual",
                             report_raw=self._with_provenance(claim))

        # -- provenance must agree with the ordinary Review Metadata ---------
        with self.subTest("provenance contradicts the Metadata commit"):
            self._reject(needle="reviewed_commit",
                         report_raw=self._with_provenance(
                             dict(self._provenance(), reviewed_commit=SHA)))
        with self.subTest("provenance contradicts the Metadata Plan hash"):
            self._reject(needle="plan_sha256",
                         report_raw=self._with_provenance(
                             dict(self._provenance(), plan_sha256=SHA)))
        with self.subTest("a report bound to a different Plan is rejected"):
            self._reject(needle="plan",
                         report_raw=self._report_raw("pass", plan_sha=SHA))

        # -- captured identities: the context manifest and its inputs --------
        with self.subTest("context hash does not cover the manifest bytes"):
            self._reject(needle="context",
                         report_raw=self._with_provenance(
                             dict(self._provenance(), context_sha256=SHA)))
        with self.subTest("a re-serialised manifest breaks the context hash"):
            raw = self._read_bytes(self._meta("context.json"))
            reserialized = json.dumps(json.loads(raw.decode("utf-8")),
                                      indent=4, sort_keys=True).encode("utf-8")
            self.assertNotEqual(reserialized, raw)
            with self._tampered(self._meta("context.json"), reserialized):
                self._reject(needle="context", report_raw=truthful)
        with self.subTest("an input claim is missing"):
            claim = self._provenance()
            claim["input_hashes"].pop(sorted(claim["input_hashes"])[0])
            self._reject(needle="input", report_raw=self._with_provenance(claim))
        with self.subTest("an input claim disagrees"):
            claim = self._provenance()
            key = sorted(claim["input_hashes"])[0]
            claim["input_hashes"][key] = SHA
            self._reject(needle="input", report_raw=self._with_provenance(claim))

        # -- a truthful report, including a genuinely failed run, holds ------
        with self.subTest("a truthful failed baseline stays valid evidence"):
            self.assertEqual(self.receipts[0]["exit_code"], 3,
                             "the fixture's baseline never actually failed")
            message = self._guarded(report_raw=truthful)
            self.assertIn("pass", message)
            published = self.read_state()["review"]
            self.assertEqual(published["verdict"], "pass")
            self.assertEqual(published["artifact_sha256"], _sha(truthful),
                             "the published binding is not the reviewer's bytes")
            self.assertEqual(self._read_bytes(self._live("review.md")), truthful)
            self.assertEqual(contracts.read_review_provenance(
                self._read_bytes(self._live("review.md"))), self._provenance())

    # ========================================================================
    # 2. Historical bindings keep their behaviour and gain no invented proof.
    # ========================================================================

    def test_legacy_binding_has_no_invented_provenance(self):
        self._fixture()
        legacy_review = self._read_bytes(self._live("review.md"))
        records_before = self._record_bytes()
        claim_before = self.read_state().get("provenance")

        with self.subTest("an old report is accepted unchanged"):
            proc = self.cli("set-review", self.TICKET, "--verdict", "pass")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            data = self.read_state()
            self.assertEqual(sorted(data["review"]),
                             ["artifact_sha256", "plan_sha256",
                              "reviewed_commit", "verdict"],
                             "the guarded work changed the legacy binding shape")
            self.assertEqual(data["review"]["verdict"], "pass")
            self.assertEqual(data["review"]["reviewed_commit"], self.reviewed)
            self.assertEqual(data["review"]["plan_sha256"], self._plan_sha())
            self.assertEqual(data["workflow_version"], 2)
            self.assertEqual(data["schema_version"], 1)
            self.assertEqual(data["phase"], "review")
            # The State's own `provenance` block (last_harness/last_model) is the
            # claim record, not isolation evidence: an unguarded record leaves it
            # exactly as it was and adds no isolation field anywhere.
            self.assertEqual(data.get("provenance"), claim_before,
                             "a legacy record invented claim provenance")
            self.assertNotIn("isolation", json.dumps(data).lower())
            self.assertEqual(self._read_bytes(self._live("review.md")),
                             legacy_review,
                             "legacy set-review rewrote the Report bytes")
            self.assertIsNone(contracts.read_review_provenance(legacy_review),
                              "a legacy report gained an invented provenance")

        with self.subTest("versions and binding survive a repeat call"):
            proc = self.cli("set-review", self.TICKET, "--verdict", "pass")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            data = self.read_state()
            self.assertEqual(data["workflow_version"], 2)
            self.assertEqual(data["schema_version"], 1)
            self.assertEqual(sorted(data["review"]),
                             ["artifact_sha256", "plan_sha256",
                              "reviewed_commit", "verdict"])
            self.assertEqual(data["review"], json.loads(
                json.dumps(data["review"])))

        marked_path = self._live("review.md")
        marked = self._report_raw("pass")
        with self.subTest("a marked report rejects ordinary unguarded "
                          "set-review"):
            self._write_bytes(marked_path, marked)
            before = self._record_bytes()
            proc = self.cli("set-review", self.TICKET, "--verdict", "pass")
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertIn("--review-context", proc.stderr)
            self.assertEqual(self._record_bytes(), before,
                             "an ordinary set-review published a marked report")

        with self.subTest("guarded publication of an unmarked report invents "
                          "nothing"):
            before = self._record_bytes()
            # Every `state.save` stamps `updated_at`, so the bytes to compare
            # against are the ones the last legitimate legacy call left — not
            # the ones from before it. What this leg proves is that the
            # rejected guarded publication added nothing on top.
            state_now = self.state_bytes()
            message = self._reject(needle="provenance", report_raw=legacy_review)
            self.assertNotIn("invented", message)
            self.assertEqual(self._record_bytes(), before)
            self.assertEqual(self.state_bytes(), state_now,
                             "a rejected guarded publication rewrote State")

        with self.subTest("a malformed reserved section is not treated as "
                          "legacy"):
            broken = (marked.decode("utf-8").split(
                "## Isolation provenance")[0]
                + "## Isolation provenance\n\n```json\n{}\n```\n")
            self._write_bytes(marked_path, broken)
            before = self._record_bytes()
            proc = self.cli("set-review", self.TICKET, "--verdict", "pass")
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertEqual(self._record_bytes(), before)

        with self.subTest("the historical binding still invalidates later drift"):
            self._write_bytes(marked_path, legacy_review)
            proc = self.cli("set-review", self.TICKET, "--verdict", "pass")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            with open(self._live("review.md"), "a", encoding="utf-8",
                      newline="") as fh:
                fh.write("\n<!-- edited after the verdict -->\n")
            validate_proc = self.cli("validate", self.TICKET)
            self.assertEqual(validate_proc.returncode, 1,
                             validate_proc.stdout + validate_proc.stderr)
            self.assertIn("Review artifact changed", validate_proc.stdout)

    # ========================================================================
    # 3. Drift refuses publication and an interrupted one recovers.
    # ========================================================================

    def test_publication_drift_and_recovery(self):
        self._fixture()
        records_before = self._record_bytes()
        verdict_before = self.read_state().get("review")
        prepared_head = self._head()

        def refuse():
            """Assert the guarded publication refused and changed nothing.

            Live bytes deliberately drifted by the leg itself are restored before
            the record comparison, and the restore writes the captured bytes
            rather than `git checkout`: this host's `core.autocrlf` makes a
            checkout re-encode the file, which would drift the captured manifest
            for every later leg instead of proving anything about publication.
            """
            proc = self._cli_guarded()
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertEqual(self._strays(), [],
                             "a rejected publication left a temporary record")
            self.assertEqual(self.read_state().get("review"), verdict_before,
                             "a rejected publication recorded a verdict")
            return proc

        with self.subTest("live code changed since the reviewed commit"):
            feature = os.path.join(self.root, "src", "feature.py")
            original = self._read_bytes(feature)
            try:
                self._write_bytes(feature, "def feature():\n    return 7\n")
                refuse()
            finally:
                self._write_bytes(feature, original)
            self.assertEqual(self._record_bytes(), records_before)

        with self.subTest("an index-hinted equal-size edit still rejects"):
            feature = os.path.join(self.root, "src", "feature.py")
            original = self._read_bytes(feature)
            self._flagged_edit("both")
            try:
                refuse()
            finally:
                self._clear_flag("src/feature.py", "both")
                self._write_bytes(feature, original)
            self.assertEqual(self._read_bytes(feature), original)
            self.assertEqual(self._record_bytes(), records_before)

        with self.subTest("the registered Plan changed"):
            plan_rel = ((self.read_state().get("source_artifacts") or {})
                        .get("plan") or {}).get("path")
            plan_path = os.path.join(self.root, *plan_rel.split("/"))
            original = self._read_bytes(plan_path)
            try:
                self._write_bytes(plan_path, original + b"\n")
                refuse()
            finally:
                self._write_bytes(plan_path, original)
            self.assertEqual(self._read_bytes(plan_path), original)

        with self.subTest("a captured verification input changed"):
            input_rel = sorted(key for key in self.context["inputs"]
                               if not key.endswith(".yaml"))[0]
            full = os.path.join(self.root, *input_rel.split("/"))
            original = self._read_bytes(full)
            try:
                self._write_bytes(full, original + b"<!-- edited -->\n")
                refuse()
            finally:
                self._write_bytes(full, original)
            self.assertEqual(self._record_bytes(), records_before)

        with self.subTest("the live State changed after preparation"):
            state_path = self._state_path()
            original = self._read_bytes(state_path)
            try:
                self._write_bytes(state_path, original + b"drifted_field: yes\n")
                refuse()
            finally:
                self._write_bytes(state_path, original)
            self.assertEqual(self.state_bytes(), original)
            self.assertEqual(self._record_bytes(), records_before)

        with self.subTest("HEAD moved past the reviewed commit"):
            self.commit_code("src/later.py", "LATER = True\n")
            try:
                refuse()
            finally:
                # `--mixed` moves HEAD and the index without re-writing any
                # worktree byte, so the captured manifest comes back exactly.
                self.assertEqual(self._git("reset", "--mixed",
                                           prepared_head).returncode, 0)
                stray = os.path.join(self.root, "src", "later.py")
                if os.path.exists(stray):
                    os.remove(stray)
            self.assertEqual(self._head(), prepared_head)
            self.assertEqual(self._record_bytes(), records_before)

        # -- an invalid candidate rejects before any live write ---------------
        with self.subTest("an invalid candidate Handoff rejects before writes"):
            self._reject(needle="handoff",
                         handoff_raw=scaffold_handoff(self.TICKET).encode("utf-8"))
        with self.subTest("a non-UTF-8 candidate Handoff rejects before "
                          "writes, decoded and named"):
            message = self._reject(
                needle="UTF-8",
                handoff_raw=b"\xff\xfethe candidate handoff is not text\n")
            self.assertIn("Handoff", message,
                          "the refusal did not name the payload it decoded")
        with self.subTest("an invalid candidate Report rejects before writes"):
            renamed = self._report_raw("pass").decode("utf-8").replace(
                "## Acceptance results", "## Acceptance notes")
            self._reject(needle="review", report_raw=renamed.encode("utf-8"))

        # -- injected write/replace failures recover byte-exactly ------------
        for where in ("stage-state", "temp", "replace-handoff", "replace-review",
                      "replace-state"):
            with self.subTest("injected %s failure" % where):
                records = self._record_bytes()
                with self._failing(where):
                    with self.assertRaises(mutate.MutateError):
                        self._guarded()
                self.assertEqual(self._record_bytes(), records,
                                 "%s failure did not recover byte-exactly" % where)
                self.assertEqual(self._strays(), [])
                self.assertEqual(review_publication.journals(self.output), [],
                                 "%s failure left an unfinished journal" % where)

        # -- a foreign concurrent writer is never overwritten ----------------
        records = self._record_bytes()
        handoff_rel = self._key(records, "handoff")
        review_rel = self._key(records, "review.md")
        state_rel = self._key(records, ".yaml")
        review_path = os.path.join(self.root, *review_rel.split("/"))
        foreign = b"written by another publisher mid-transaction\n"
        candidate = self._report_raw("pass")
        with self.subTest("a foreign concurrent edit is never overwritten"):
            with self._hijacking(foreign):
                with self.assertRaises(mutate.MutateError) as ctx:
                    self._guarded(report_raw=candidate)
            self.assertIn("journal", str(ctx.exception))
            self.assertEqual(self._read_bytes(os.path.join(
                self.root, *handoff_rel.split("/"))), records[handoff_rel],
                "an owned Handoff write was not recovered")
            self.assertEqual(self._read_bytes(review_path), foreign,
                "recovery overwrote a foreign record edit")
            self.assertEqual(self._read_bytes(os.path.join(
                self.root, *state_rel.split("/"))), records[state_rel],
                "State was replaced although it is the commit marker")
            self.assertTrue(review_publication.journals(self.output),
                            "an unrecoverable transaction discarded its journal")

        with self.subTest("an unfinished journal is recovered before reuse"):
            journals = review_publication.journals(self.output)
            self.assertEqual(len(journals), 1)
            # Resolve the conflict the only way a coordinator may: hand back the
            # bytes the interrupted transaction owned, then recover.
            self._write_bytes(review_path, candidate)
            recovered = review_publication.recover_stray_journals(self.output)
            self.assertEqual(recovered, [os.path.realpath(journals[0])])
            self.assertEqual(self._read_bytes(review_path), records[review_rel],
                             "recovery did not restore the original bytes exactly")
            self.assertEqual(review_publication.journals(self.output), [])

        with self.subTest("an unrecoverable journal blocks publication"):
            planted = self._plant_journal(records)
            before = self._record_bytes()
            with self.assertRaises(mutate.MutateError) as ctx:
                self._guarded()
            self.assertIn("journal", str(ctx.exception))
            self.assertEqual(self._record_bytes(), before,
                             "a blocked recovery still wrote a record")
            self.assertTrue(os.path.exists(planted),
                            "a blocked publication discarded the journal")
            os.remove(planted)
            os.rmdir(os.path.dirname(planted))
            self._write_bytes(os.path.join(self.root, *review_rel.split("/")),
                              records[review_rel])
            self.assertEqual(self._record_bytes(), records)

        with self.subTest("restored live records publish after every refusal"):
            proc = self._cli_guarded()
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertNotEqual(self._record_bytes(), records_before)

    class _Injected(OSError):
        """What an injected write/replace failure looks like to the publisher."""

    @contextlib.contextmanager
    def _failing(self, where):
        """Fail one publisher write seam, the way a full disk would."""
        def fail(*args, **kwargs):
            raise ReviewPublicationTest._Injected(5, "injected write failure")

        targets = {"stage-state": ("_stage_state", fail),
                   "temp": ("_write_bytes", fail),
                   "replace-handoff": ("_replace", self._replace_for("handoff")),
                   "replace-review": ("_replace", self._replace_for("review")),
                   "replace-state": ("_replace", self._replace_for("state"))}
        name, side_effect = targets[where]
        with mock.patch.object(review_publication, name, side_effect=side_effect):
            yield

    @staticmethod
    def _replace_for(record):
        """Raise only on the named record's replace, letting the others pass."""
        def side_effect(src, dst):
            if record in os.path.basename(dst):
                raise ReviewPublicationTest._Injected(
                    5, "injected replace failure for %s" % record)
            return os.replace(src, dst)

        return side_effect

    @contextlib.contextmanager
    def _hijacking(self, foreign):
        """Let the transaction write, clobber Review, then fail the commit."""
        real_replace = review_publication._replace
        review_path = self._live("review.md")

        def side_effect(src, dst):
            real_replace(src, dst)
            name = os.path.basename(dst)
            if name.startswith("review"):
                # Another writer reaches the same record inside the window.
                self._write_bytes(review_path, foreign)
            if name.startswith("state"):
                raise ReviewPublicationTest._Injected(
                    5, "injected failure at the commit marker")

        with mock.patch.object(review_publication, "_replace",
                               side_effect=side_effect):
            yield

    def _plant_journal(self, records):
        """Write a supervisor-style journal whose backup bytes were destroyed."""
        review_rel = self._key(records, "review.md")
        review_path = os.path.join(self.root, *review_rel.split("/"))
        owned = b"owned bytes from an interrupted publisher\n"
        self._write_bytes(review_path, owned)
        directory = os.path.join(self._meta("publication"), "planted")
        os.makedirs(directory)
        backup = os.path.join(directory, "review.backup")
        self._write_bytes(backup, records[review_rel])
        journal = os.path.join(directory, "journal.json")
        self._write_bytes(journal, json.dumps({
            "format_version": review_publication.JOURNAL_FORMAT_VERSION,
            "ticket_id": self.TICKET,
            "reviewed_commit": self.context["reviewed_commit"],
            "records": [{
                "record": "review",
                "path": review_rel,
                "old_sha256": _sha(records[review_rel]),
                "owned_sha256": _sha(owned),
                "backup_path": backup,
            }],
        }, indent=2, sort_keys=True).encode("utf-8"))
        os.remove(backup)  # the damage that makes recovery impossible
        return journal

    # ========================================================================
    # 4. The author's verdict, bytes and phase stay exactly as published.
    # ========================================================================

    def _reset_fixture(self, verdict):
        """A fresh review context per verdict in the same throwaway repository.

        `prepare_v2_review` re-drives the public lifecycle, so the completed-task
        counters are zeroed first (a second `complete-task` over a finished Plan is
        a genuine refusal, not this fixture's business) and every context gets its
        own previously-absent output directory.
        """
        data = self.read_state()
        data["implementation"] = {"current_task": 0, "total_tasks": 0,
                                  "completed_tasks": [], "task_hashes": []}
        self.write_state(data)
        self._fixture(verdict=verdict, extension=True)

    def test_guarded_publication_preserves_author_and_phase(self):
        for verdict in ("pass", "changes_requested"):
            with self.subTest(verdict=verdict):
                self._reset_fixture(verdict)
                report_raw = self._report_raw(verdict)
                handoff_raw = self._handoff_raw()
                records_before = self._record_bytes()
                state_before = self.read_state()
                index_before = self._index_record()
                source_before = self._source_bytes()
                work_before = sorted(os.listdir(os.path.join(self.root, ".ai",
                                                             "work",
                                                             self.TICKET)))

                proc = self._cli_guarded(verdict, report_raw=report_raw,
                                         handoff_raw=handoff_raw)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

                published_bytes = self._read_bytes(self._live("review.md"))
                self.assertEqual(published_bytes, report_raw,
                                 "the published Review is not the reviewer's "
                                 "exact raw bytes")
                self.assertEqual(_sha(published_bytes), _sha(report_raw))
                self.assertEqual(contracts.read_review_provenance(published_bytes),
                                 self._provenance())

                state_after = self.read_state()
                self.assertEqual(state_after["phase"], state_before["phase"])
                self.assertEqual(state_after["review"]["verdict"], verdict)
                self.assertEqual(state_after["review"]["artifact_sha256"],
                                 _sha(report_raw))
                self.assertEqual(state_after["review"]["reviewed_commit"],
                                 self.context["reviewed_commit"])
                self.assertTrue(FULL_OID_RE.match(
                    state_after["review"]["reviewed_commit"]))
                self.assertEqual(state_after["review"]["plan_sha256"],
                                 self._plan_sha())
                self.assertEqual(sorted(state_after["review"]),
                                 ["artifact_sha256", "plan_sha256",
                                  "reviewed_commit", "verdict"])
                self.assertEqual(state_after["implementation"],
                                 state_before["implementation"])
                self.assertEqual(state_after["next_action"],
                                 state_before["next_action"])
                self.assertEqual(state_after["status"], state_before["status"])
                self.assertEqual(state_after["workflow_version"], 2)
                self.assertEqual(state_after["schema_version"], 1)
                self.assertEqual(state_after["extension_evidence"],
                                 {"note": "preserve me", "count": 3},
                                 "publication dropped an unknown extension field")
                self.assertNotIn("isolation", json.dumps(state_after).lower())

                self.assertEqual(self._source_bytes(), source_before,
                                 "publication repaired source code")
                self.assertEqual(self._index_record(), index_before,
                                 "publication moved the Git index")
                self.assertEqual(sorted(os.listdir(os.path.join(
                    self.root, ".ai", "work", self.TICKET))), work_before,
                    "publication wrote an unexpected record")
                self.assertEqual(sorted(self._record_bytes()),
                                 sorted(records_before))
                self.assertEqual(self._strays(), [])

                # Live HEAD is reported alongside the reviewed commit.
                self.assertIn(self._head(), proc.stdout)
                self.assertIn(self.context["reviewed_commit"], proc.stdout)
                records = review_publication.publication_records(self.output)
                self.assertEqual(len(records), 1,
                                 "publication wrote no supervisor record")
                record = json.loads(self._read_bytes(records[0]).decode("utf-8"))
                self.assertEqual(record["live_head"], self._head())
                self.assertEqual(record["reviewed_commit"],
                                 self.context["reviewed_commit"])
                self.assertEqual(record["verdict"], verdict)
                self.assertEqual(sorted(entry["record"]
                                         for entry in record["records"]),
                                 ["handoff", "review", "state"])

                # Existing consumers still accept the published binding.
                proc = self.cli("validate", self.TICKET)
                self.assertNotIn("stale", proc.stdout)
                self.assertNotIn("Traceback", proc.stderr)
                if verdict == "pass":
                    self.assertEqual(proc.returncode, 0,
                                     proc.stdout + proc.stderr)

                # A publication consumes its context: State and Handoff are
                # captured inputs, so the very same candidate may not be
                # published a second time against one prepared run. Proved,
                # not assumed — the second attempt must refuse and write
                # nothing.
                records_after_first = self._record_bytes()
                proc = self._cli_guarded(verdict, report_raw=report_raw,
                                         handoff_raw=handoff_raw)
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)
                self.assertIn("changed since the review context was prepared",
                              proc.stderr)
                self.assertEqual(self._record_bytes(), records_after_first,
                                 "the refused second publication rewrote a "
                                 "record")
                self.assertEqual(self._strays(), [])

    def _index_record(self):
        index_path = os.path.join(self.root, ".git", "index")
        with open(index_path, "rb") as fh:
            return {"index": fh.read(),
                    "flags": self._git("ls-files", "-v", "-z").stdout}

    def _source_bytes(self):
        out = {}
        for rel in ("src/feature.py", "src/app.py", "src/other.py"):
            full = os.path.join(self.root, *rel.split("/"))
            if os.path.exists(full):
                out[rel] = self._read_bytes(full)
        plan_rel = ((self.read_state().get("source_artifacts") or {})
                    .get("plan") or {}).get("path")
        if plan_rel:
            out[plan_rel] = self._read_bytes(os.path.join(self.root,
                                                          *plan_rel.split("/")))
        return out

    # ========================================================================
    # 5. The guarded CLI surface is additive and strictly all-or-nothing.
    # ========================================================================

    def test_guarded_options_are_required_together(self):
        self._fixture(with_evidence=False)
        records = self._record_bytes()
        report_raw = self._report_raw("pass", provenance=None)
        report_path, handoff_path = self._write_candidate(report_raw,
                                                         self._handoff_raw())
        for args in (["--verdict", "pass", "--review-context", self.output],
                     ["--verdict", "pass", "--review-context", self.output,
                      "--report", report_path],
                     ["--verdict", "pass", "--report", report_path,
                      "--handoff", handoff_path]):
            with self.subTest(args):
                proc = self.cli("set-review", self.TICKET, *args)
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertIn("together", proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)
                self.assertEqual(self._record_bytes(), records)
        proc = self.cli("set-review")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)

    def test_publish_api_never_supplies_a_verdict_or_advances(self):
        self._fixture()
        report_raw = self._report_raw("changes_requested")
        data = self.read_state()
        report = contracts.parse_artifact(report_raw, "review")
        proposed = mutate._review_candidate(self.root, self.TICKET, data, report,
                                           report_raw, "changes_requested")
        self.assertEqual(proposed["review"]["verdict"], "changes_requested")
        self.assertEqual(proposed["review"]["artifact_sha256"], _sha(report_raw))
        self.assertIsNot(proposed, data, "_review_candidate returned the same dict")
        self.assertEqual(self.read_state(), data,
                         "_review_candidate is not pure: it changed live State")
        before = self._record_bytes()
        self.assertIsNone(review_publication.publish(
            self.root, self.TICKET, self.output, report_raw,
            self._handoff_raw(), proposed))
        after = self._record_bytes()
        self.assertNotEqual(after, before)
        published = self.read_state()
        self.assertEqual(published["review"], proposed["review"])
        self.assertEqual(published["phase"], "review")
        self.assertEqual(published["implementation"], data["implementation"])
        self.assertEqual(self._read_bytes(self._live("review.md")), report_raw)

    # ========================================================================
    # 6. The context lock serializes publishers and does not seal a context.
    # ========================================================================

    def test_publication_lock_is_exclusive_and_breaks_a_stale_one(self):
        """A live second publisher holds the context; a wedged one never seals it.

        The contending holder is real in the way the lock itself can observe:
        the lock file exists, written by another `_Lock` token, with a fresh
        mtime. The waiting publisher then runs its real acquire loop (a short
        patched timeout — the refusal logic itself is untouched), so this
        proves exclusivity without a flaky two-thread race. The second leg
        backdates the same lock beyond `_LOCK_STALE_AFTER` and shows a real
        publication breaking it and completing.
        """
        self._fixture()
        records = self._record_bytes()
        lock_path = os.path.join(self._meta("publication"), "lock")
        live_holder = json.dumps({"token": "another-publisher",
                                  "ticket_id": self.TICKET,
                                  "pid": os.getpid(),
                                  "acquired_at": "2026-10-10T00:00:00+00:00"},
                                 sort_keys=True).encode("utf-8")
        self._write_bytes(lock_path, live_holder)
        with self.subTest("a live second publisher refuses, never steals"):
            with mock.patch.object(review_publication, "_LOCK_TIMEOUT", 0.2):
                message = self._reject(needle="publication-busy",
                                       records=records)
            self.assertIn("serialized", message)
            self.assertIn("lock", message)
            self.assertEqual(self._read_bytes(lock_path), live_holder,
                             "a waiting publisher removed a lock it never held")
            self.assertEqual(self._record_bytes(), records)
            self.assertEqual(review_publication.journals(self.output), [],
                             "the refused publisher opened a journal")
        with self.subTest("a lock older than any live transaction is broken"):
            past = time.time() - (review_publication._LOCK_STALE_AFTER + 60.0)
            os.utime(lock_path, (past, past))
            message = self._guarded()
            self.assertIn("published", message)
            self.assertFalse(os.path.exists(lock_path),
                             "the publisher left its own lock behind")
            self.assertEqual(review_publication.journals(self.output), [])
            state_after = self.read_state()
            self.assertEqual(state_after["review"]["verdict"], "pass")
            self.assertNotEqual(self._record_bytes(), records,
                                "breaking the stale lock published nothing")


if __name__ == "__main__":
    unittest.main()
