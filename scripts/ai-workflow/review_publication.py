"""Guarded publication of an isolated review candidate (HARDEN-011 Task 3).

A reviewer working inside the Task 1 snapshot and under the Task 2 boundary
produces a *candidate* Report and Handoff. Nothing it writes can reach the live
workflow records directly. This module is the only door: it validates the
candidate, proves the report's declared isolation provenance against the
supervisor's own receipts, re-checks that the live baseline is still the one that
was captured, and then publishes **only** the configured Review, State and
Handoff records.

What is published, and what is never decided here
------------------------------------------------
The verdict is the Reviewer's, supplied by the caller through the ordinary
`mutate._review_candidate` binding. This module never invents one, never repairs
source, never advances a phase and never touches any other record: a proposed
State that changes anything beyond the review binding, the `artifacts.review`
default and the serializer's `updated_at` stamp is refused outright.

What "validated" means, plainly
------------------------------
Structure establishes conformance, not truth. The report's `limits`, its nested
inner commands and its probe before/after hashes are **reviewer-authored claims**
and stay claims: no amount of shape checking makes them proof. What *is* checked
against supervisor-owned records is the identity chain — the context manifest
bytes, the captured live/snapshot manifest identities, every captured input hash,
the persisted boundary evidence, and each claimed run against
`meta/runs/<run_id>.json` (argv, exit status, output hashes and the before/after
snapshot identities). A claim that the records do not support is rejected, which
is the whole point: a report can fail, but it cannot upgrade itself.

Specifically rejected: an enforced-boundary claim with no matching supervisor
evidence; a report that does not distinguish a baseline run from a probe run; an
absent or mismatched receipt; a probe path that is not repository-relative inside
the snapshot or that no receipt names; a claim of success for a command whose
receipt records a nonzero exit; and residual snapshot changes the receipt says are
still there but the report says are not. **A truthful failed run stays valid
evidence** — whether that failure blocks acceptance is the human technical
verdict's decision, not this validator's.

Publication is recoverable, not atomic
-------------------------------------
The transaction stages the proposed State privately through the kit's own
`state.save_file` (so unknown extension fields and serializer behaviour survive
exactly), serializes publishers per context with a lock inside the supervisor's
`meta/`, rechecks the old record identities, then replaces Handoff and Review
first and State **last** as the binding commit marker, using adjacent unique
temporary files, and finally rechecks the live identities.

Say the limit plainly: this is *recoverable* publication. It is not a promise that
the three records become visible atomically, and it does not serialize against
arbitrary external writers. On a failure only a file still holding this
transaction's own bytes is restored — a foreign or intervening writer's file is
never overwritten — and a transaction that could not fully recover leaves its
journal, which the next publisher must recover or be blocked by. A concurrent
external writer therefore yields a conflict or a stale review, never an
automatically refreshed pass. A preflight or currentness mismatch performs zero
live record writes.

Python 3 stdlib only; Git and every command run through argument lists, never a
shell.
"""

import copy
import datetime
import errno
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import uuid

import contracts
import review
import review_boundary
import review_snapshot
import state
import workflow_v2

__all__ = ["publish", "journals", "publication_records",
           "recover_stray_journals", "live_head", "JOURNAL_FORMAT_VERSION"]

JOURNAL_FORMAT_VERSION = 1
RECORD_FORMAT_VERSION = 1

# Context layout, as written by Tasks 1 and 2. Repeated here as private names so
# this module reads only what the supervisor owns and never reaches into another
# module's internals.
_META_DIR = "meta"
_CONTEXT_FILE = "context.json"
_PREFLIGHT_FILE = "preflight.json"
_RUNS_DIR = "runs"
_PUBLICATION_DIR = "publication"
_JOURNAL_FILE = "journal.json"
_RECORD_FILE = "record.json"
_BACKUP_DIR = "backup"
_LOCK_FILE = "lock"

# Handoff and Review first, State last: State is the commit marker, so a
# transaction that never reached State provably published nothing binding.
_RECORD_ORDER = ("handoff", "review", "state")
_TEMP_FORMAT = ".ai-workflow-publish-%s.tmp"
_VERDICTS = ("pass", "changes_requested")
_RECEIPT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
# A publisher that died mid-transaction leaves its lock behind; a live one never
# holds it for long, so an older lock is broken rather than waited on forever.
_LOCK_TIMEOUT = 10.0
_LOCK_POLL = 0.02
_LOCK_STALE_AFTER = 120.0

# Named refusals: greppable, and each one says what the publisher needed.
REASON_VERDICT = "verdict-absent"
REASON_BINDING = "binding-mismatch"
REASON_STATE_SCOPE = "publication-would-advance"
REASON_STALE = "publication-stale"
REASON_CONTEXT = "context-identity-mismatch"
REASON_INPUTS = "input-hash-mismatch"
REASON_METADATA = "metadata-contradiction"
REASON_BOUNDARY = "unenforced-boundary-claim"
REASON_PROFILE = "boundary-profile-mismatch"
REASON_RECEIPT_ABSENT = "receipt-absent"
REASON_RECEIPT_MISMATCH = "receipt-mismatch"
REASON_FALSE_SUCCESS = "receipt-claimed-success"
REASON_RUNS = "run-kinds-indistinct"
REASON_PROBE_UNNAMED = "probe-change-unnamed"
REASON_RESIDUAL = "residual-changes-erased"
REASON_HANDOFF = "candidate-handoff-not-ready"
REASON_JOURNAL = "publication-journal-incomplete"
REASON_LOCK = "publication-busy"
REASON_CONFLICT = "publication-conflict"
REASON_WRITE = "publication-write-failed"


# ---------------------------------------------------------------------------
# Small IO seams. The focused tests inject failures here, which is how an
# interrupted replace is exercised without damaging a real disk.
# ---------------------------------------------------------------------------

def _read_bytes(path):
    """Read a file's raw bytes; unreadable is a ContractError, never a guess."""
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as exc:
        raise contracts.ContractError("cannot read %r: %s" % (path, exc))


def _read_bytes_or_none(path):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def _write_bytes(path, payload):
    """Write bytes through a private temporary file, then move them into place."""
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        try:
            os.makedirs(parent)
        except OSError as exc:
            raise contracts.ContractError("cannot create %r: %s" % (parent, exc))
    tmp = path + ".tmp"
    try:
        with open(tmp, "wb") as fh:
            fh.write(payload)
        os.replace(tmp, path)
    except OSError as exc:
        raise contracts.ContractError("cannot write %r: %s" % (path, exc))


def _replace(src, dst):
    """The one publishing primitive: atomically move a prepared file into place."""
    try:
        os.replace(src, dst)
    except OSError as exc:
        raise contracts.ContractError("cannot publish %r over %r: %s"
                                      % (src, dst, exc))


def _remove_file(path):
    try:
        if os.path.lexists(path):
            os.remove(path)
    except OSError as exc:
        raise contracts.ContractError("cannot remove %r: %s" % (path, exc))


def _stage_state(path, data):
    """Serialize the proposed State privately, through the kit's own writer.

    `state.save_file` is the only State serializer in this kit: using it here is
    what preserves unknown extension fields and its exact output behaviour,
    instead of a second writer that could drift from the first.
    """
    try:
        state.save_file(path, data)
    except (state.StateError, OSError) as exc:
        raise contracts.ContractError("cannot stage the proposed State: %s" % exc)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _sha_or_none(raw):
    return None if raw is None else _sha(raw)


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _load_json(path, what):
    try:
        return json.loads(_read_bytes(path).decode("utf-8"))
    except ValueError as exc:
        raise contracts.ContractError("%s is not readable JSON (%s): %s"
                                      % (what, path, exc))


def live_head(root):
    """The live repository's current HEAD, reported alongside reviewed_commit.

    `review_snapshot.assert_current` and `review.binding_problems` are
    deliberately content-based and never compare HEAD to the reviewed commit —
    a later commit that changes nothing in scope is still current. Currentness
    reporting still has to say which HEAD it spoke about, so publication records
    and reports name `live_head` next to `reviewed_commit` instead of implying
    they are the same thing.
    """
    try:
        proc = subprocess.run(["git", "--no-optional-locks", "-C", root,
                               "rev-parse", "HEAD"], capture_output=True)
    except OSError as exc:
        raise contracts.ContractError("git is not available: %s" % exc)
    if proc.returncode != 0:
        raise contracts.ContractError(
            "cannot resolve the live HEAD: %s"
            % proc.stderr.decode("utf-8", "replace").strip())
    return proc.stdout.decode("utf-8", "replace").strip()


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

def _publication_dir(context_path):
    return os.path.join(context_path, _META_DIR, _PUBLICATION_DIR)


def _journal_entries(path):
    found = []
    base = _publication_dir(path)
    if not os.path.isdir(base):
        return found
    for name in sorted(os.listdir(base)):
        entry = os.path.join(base, name)
        if os.path.isdir(entry):
            candidate = os.path.join(entry, _JOURNAL_FILE)
            if os.path.isfile(candidate):
                found.append(candidate)
        elif name.endswith(".journal.json"):
            found.append(entry)
    return sorted(found)


def journals(context_path):
    """Paths of surviving publication journals — unfinished transactions.

    A journal is left behind only when a transaction could not be rolled back,
    which is exactly the state a new publication must resolve first; exposing
    the list is how the state stays inspectable instead of silent.
    """
    return _journal_entries(context_path)


def publication_records(context_path):
    """Paths of the supervisor's completed publication records, oldest first."""
    base = _publication_dir(context_path)
    found = []
    if not os.path.isdir(base):
        return found
    for name in sorted(os.listdir(base)):
        candidate = os.path.join(base, name, _RECORD_FILE)
        if os.path.isfile(candidate):
            found.append(candidate)
    return found


def _record_target(root, ticket_id, data, key, default):
    """The absolute path of one configured record, refused if it escapes."""
    artifacts = data.get("artifacts") or {}
    name = artifacts.get(key, default)
    if not isinstance(name, str) or not name or os.path.isabs(name):
        raise contracts.ContractError(
            "the configured %r artifact %r is not a file inside the Ticket "
            "work directory" % (key, name))
    rel = ".ai/work/%s/%s" % (ticket_id, name)
    if ".." in rel.split("/"):
        raise contracts.ContractError(
            "the configured %r artifact %r escapes the Ticket work directory"
            % (key, name))
    return rel, os.path.join(root, *rel.split("/"))


def _record_paths(root, ticket_id, data):
    """{record: (repository-relative path, absolute path)} for the three."""
    paths = {"state": (".ai/work/%s/state.yaml" % ticket_id,
                       os.path.join(root, ".ai", "work", ticket_id,
                                    "state.yaml"))}
    paths["review"] = _record_target(root, ticket_id, data, "review", "review.md")
    paths["handoff"] = _record_target(root, ticket_id, data, "handoff",
                                      "handoff.md")
    for record, (_rel, absolute) in paths.items():
        if os.path.islink(absolute):
            raise contracts.ContractError(
                "the %s record %r is a symlink; publication follows links into "
                "no record" % (record, absolute))
    return paths


# ---------------------------------------------------------------------------
# Lock: publisher activity is serialized per context
# ---------------------------------------------------------------------------

class _Lock:
    """An exclusive create-lock in the supervisor-owned meta area."""

    def __init__(self, context_path, ticket_id):
        self.path = os.path.join(_publication_dir(context_path), _LOCK_FILE)
        self.ticket_id = ticket_id
        self.token = uuid.uuid4().hex
        self.held = False

    def acquire(self):
        directory = os.path.dirname(self.path)
        try:
            if not os.path.isdir(directory):
                os.makedirs(directory)
        except OSError as exc:
            raise contracts.ContractError(
                "cannot create the publication directory %r: %s"
                % (directory, exc))
        deadline = time.monotonic() + _LOCK_TIMEOUT
        while True:
            try:
                handle = os.open(self.path,
                                 os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except OSError as exc:
                if exc.errno != errno.EEXIST:
                    raise contracts.ContractError(
                        "cannot take the publication lock %r: %s"
                        % (self.path, exc))
                if self._break_stale():
                    continue
                if time.monotonic() >= deadline:
                    raise contracts.ContractError(
                        "%s: another publication holds the review context lock "
                        "%r; publisher activity is serialized per context"
                        % (REASON_LOCK, self.path))
                time.sleep(_LOCK_POLL)
                continue
            with os.fdopen(handle, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"token": self.token,
                                     "ticket_id": self.ticket_id,
                                     "pid": os.getpid(),
                                     "acquired_at": _now()},
                                    sort_keys=True))
            self.held = True
            return self

    def _break_stale(self):
        """True when the held lock is older than any live transaction runs."""
        try:
            age = time.time() - os.stat(self.path).st_mtime
        except OSError:
            return False
        if age < _LOCK_STALE_AFTER:
            return False
        try:
            os.remove(self.path)
        except OSError:
            return False
        return True

    def release(self):
        if not self.held:
            return
        current = _read_bytes_or_none(self.path)
        if current is not None:
            try:
                holder = json.loads(current.decode("utf-8")).get("token")
            except ValueError:
                holder = None
            if holder != self.token:
                return  # someone else owns it now; it is not ours to remove
        try:
            os.remove(self.path)
        except OSError:
            pass

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc_info):
        self.release()
        return False


# ---------------------------------------------------------------------------
# Candidate consistency: what the caller must have supplied
# ---------------------------------------------------------------------------

def _require(condition, reason, detail):
    if not condition:
        raise contracts.ContractError("%s: %s" % (reason, detail))


def _candidate_verdict(proposed_state):
    block = (proposed_state or {}).get("review")
    _require(isinstance(block, dict), REASON_VERDICT,
             "the proposed State carries no review binding; the caller supplies "
             "the Reviewer's verdict and this publisher never writes one")
    verdict = block.get("verdict")
    _require(verdict in _VERDICTS, REASON_VERDICT,
             "the proposed verdict %r is not the Reviewer's own "
             "pass or changes_requested verdict" % (verdict,))
    return verdict, block


def _require_binding(verdict, block, report_raw, claim):
    _require(isinstance(block.get("artifact_sha256"), str)
             and block["artifact_sha256"] == _sha(report_raw), REASON_BINDING,
             "the recorded artifact_sha256 does not cover the candidate Report "
             "bytes, so the verdict would not bind the report being published")
    _require(isinstance(block.get("plan_sha256"), str)
             and block["plan_sha256"] == claim["plan_sha256"], REASON_BINDING,
             "the recorded plan_sha256 %r disagrees with the provenance "
             "plan_sha256 %r" % (block.get("plan_sha256"),
                                 claim["plan_sha256"]))
    _require(isinstance(block.get("reviewed_commit"), str)
             and block["reviewed_commit"] == claim["reviewed_commit"],
             REASON_BINDING,
             "the recorded reviewed_commit %r disagrees with the provenance "
             "reviewed_commit %r" % (block.get("reviewed_commit"),
                                     claim["reviewed_commit"]))


def _require_only_verdict_change(live, proposed):
    """The proposed State may differ from the live one only in the verdict.

    That is the structural form of "publication never transitions a phase and
    never repairs anything else": the counters, the route, the Status, the
    source artifact identities and every unknown extension field must be exactly
    what they were, and the only added keys are the review binding, the
    `artifacts.review` default and the serializer's `updated_at` stamp.
    """
    changed = sorted(key for key in set(live) | set(proposed)
                     if live.get(key) != proposed.get(key))
    allowed = {"review", "artifacts", "updated_at"}
    _require(set(changed) <= allowed, REASON_STATE_SCOPE,
             "the proposed State changes %s; publication writes the Review "
             "verdict only and never transitions a phase, repairs a counter or "
             "rewrites another field"
             % ", ".join(repr(key) for key in sorted(set(changed) - allowed)))
    live_artifacts = dict(live.get("artifacts") or {})
    proposed_artifacts = dict(proposed.get("artifacts") or {})
    added = {key: value for key, value in proposed_artifacts.items()
             if key not in live_artifacts}
    _require(added in ({}, {"review": "review.md"}), REASON_STATE_SCOPE,
             "the proposed State changes the configured artifacts beyond "
             "defaulting artifacts.review to review.md: %r" % (added,))
    for key in live_artifacts:
        _require(proposed_artifacts.get(key) == live_artifacts[key],
                 REASON_STATE_SCOPE,
                 "the proposed State redirects the configured %r artifact; "
                 "publication writes the records the Ticket already names"
                 % (key,))
    _require(proposed.get("phase") == live.get("phase") == "review",
             REASON_STATE_SCOPE,
             "publication keeps the retained phase: live phase=%r, proposed "
             "phase=%r" % (live.get("phase"), proposed.get("phase")))
    _require(workflow_v2.version(proposed) == 2, REASON_STATE_SCOPE,
             "guarded publication is a v2 act on a v2 Ticket")


# ---------------------------------------------------------------------------
# Provenance: the identity chain and the supervisor's receipts
# ---------------------------------------------------------------------------

def _validate_identities(manifest, claim):
    _require(claim["reviewed_commit"] == manifest.get("reviewed_commit"),
             REASON_CONTEXT,
             "the provenance reviewed_commit %r is not the commit this review "
             "context captured (%r)" % (claim["reviewed_commit"],
                                       manifest.get("reviewed_commit")))
    _require(claim["plan_sha256"] == (manifest.get("plan") or {}).get("sha256"),
             REASON_CONTEXT,
             "the provenance plan_sha256 %r is not the Plan this review context "
             "captured (%r)" % (claim["plan_sha256"],
                                (manifest.get("plan") or {}).get("sha256")))
    for key, field in (("live_manifest_sha256", "live_manifest"),
                       ("snapshot_manifest_sha256", "snapshot_manifest")):
        _require(claim[key] == manifest.get(field), REASON_CONTEXT,
                 "the provenance %s does not match the captured review context "
                 "field %s" % (key, field))
    _require(claim["input_hashes"] == manifest.get("inputs"), REASON_INPUTS,
             "the provenance input_hashes do not cover exactly the verification "
             "inputs the review context captured (claimed %r, captured %r)"
             % (sorted(claim["input_hashes"]),
                sorted(manifest.get("inputs") or {})))


def _validate_against_metadata(metadata, claim, root):
    """A provenance block that contradicts the Review Metadata is a rejection."""
    try:
        resolved = review.resolve_commit(root, metadata.get("reviewed_commit"))
    except contracts.ContractError as exc:
        raise contracts.ContractError("%s: the Review Metadata reviewed_commit "
                                      "cannot be resolved: %s"
                                      % (REASON_METADATA, exc))
    _require(resolved == claim["reviewed_commit"], REASON_METADATA,
             "the provenance reviewed_commit %r contradicts the Review Metadata "
             "reviewed_commit %r" % (claim["reviewed_commit"], resolved))
    _require(claim["plan_sha256"] == metadata.get("plan_sha256"),
             REASON_METADATA,
             "the provenance plan_sha256 %r contradicts the Review Metadata "
             "plan_sha256 %r" % (claim["plan_sha256"],
                                 metadata.get("plan_sha256")))


def _validate_boundary(context_path, claim, receipts):
    boundary = claim["boundary"]
    _require(boundary["enforced"] is True, REASON_BOUNDARY,
             "only a review run under an enforced boundary is publishable "
             "through the guarded path; this report claims enforced=false and no "
             "publication may read an unenforced run as isolation")
    evidence_path = os.path.join(context_path, _META_DIR, _PREFLIGHT_FILE)
    _require(boundary["preflight"] == "%s/%s" % (_META_DIR, _PREFLIGHT_FILE),
             REASON_BOUNDARY,
             "the report points its boundary claim at %r; the supervisor's "
             "restriction evidence is persisted at meta/preflight.json"
             % (boundary["preflight"],))
    raw = _read_bytes_or_none(evidence_path)
    _require(raw is not None, REASON_BOUNDARY,
             "the report claims an enforced boundary but the supervisor persisted "
             "no meta/preflight.json evidence for this context")
    evidence = json.loads(raw.decode("utf-8", "replace"))
    _require(isinstance(evidence, dict), REASON_BOUNDARY,
             "meta/preflight.json is not a supervisor evidence record")
    _require(_sha(raw) == boundary["preflight_sha256"], REASON_BOUNDARY,
             "the boundary claim's preflight_sha256 does not cover the bytes of "
             "the persisted meta/preflight.json")
    _require(evidence.get("enforced") is True, REASON_BOUNDARY,
             "the persisted boundary evidence does not claim enforcement "
             "(blocker=%r); an unavailable boundary produces a blocker, never a "
             "passing publication" % (evidence.get("blocker"),))
    _require(evidence.get("profile") == boundary["profile"]
             == review_boundary.PROFILE, REASON_PROFILE,
             "the claimed boundary profile %r is not the profile the supervisor "
             "evidence recorded (%r); profile %s is the only one this profile "
             "publishes" % (boundary["profile"], evidence.get("profile"),
                            review_boundary.PROFILE))
    denials = evidence.get("denials") or {}
    _require(bool(denials) and all(not attempt.get("allowed")
                                   for attempt in denials.values()),
             REASON_BOUNDARY,
             "the persisted evidence records a permitted write inside the "
             "boundary, so it proves no denial")
    # The proof set `review_boundary._evidence_is_current` requires before it
    # accepts a run (HARDEN-011 Task 2): a persisted record that no longer
    # proves the writable scopes, the network denial, the un-mounted meta or
    # the removed sentinel is not boundary evidence, however its `enforced`
    # flag reads. These are structural checks publication can make from the
    # bytes alone; the host-side re-check (bwrap version, mount roots against
    # the live layout) is the supervisor's at run time, and here the evidence
    # is pinned by its own hash through both the claim and every receipt.
    _require(evidence.get("format_version") == review_boundary.FORMAT_VERSION,
             REASON_BOUNDARY,
             "the persisted boundary evidence is not a format_version %d "
             "record" % review_boundary.FORMAT_VERSION)
    _require(evidence.get("blocker") is None, REASON_BOUNDARY,
             "the persisted boundary evidence records blocker %r; an "
             "unavailable boundary reports a blocker, never a passing "
             "publication" % (evidence.get("blocker"),))
    _require(evidence.get("meta_mounted") is False, REASON_BOUNDARY,
             "the persisted boundary evidence says the supervisor's meta was "
             "mounted inside the sandbox; run evidence from such a boundary "
             "is not isolation")
    _require(evidence.get("cwd") == review_boundary.SANDBOX_CWD,
             REASON_BOUNDARY,
             "the persisted boundary evidence was not proved with cwd %r "
             "(got %r)" % (review_boundary.SANDBOX_CWD, evidence.get("cwd")))
    writable = evidence.get("writable") or {}
    unproved = [scope for scope in review_boundary.WRITABLE_SCOPES
                if writable.get(scope) is not True]
    _require(not unproved, REASON_BOUNDARY,
             "the persisted boundary evidence proves no writable scope for %s"
             % ", ".join(repr(scope) for scope in unproved))
    _require(evidence.get("network_denied") is True
             and evidence.get("network_denial_errno")
             in review_boundary.NO_NETWORK_ERRNOS,
             REASON_BOUNDARY,
             "the persisted boundary evidence carries no network-denial proof "
             "(network_denied=%r, network_denial_errno=%r)"
             % (evidence.get("network_denied"),
                evidence.get("network_denial_errno")))
    _require((evidence.get("sentinel") or {}).get("removed") is True,
             REASON_BOUNDARY,
             "the persisted boundary evidence does not record its protected "
             "sentinel as removed")
    for key in ("supervisor_host", "sandbox_host", "cwd"):
        if key in boundary:
            _require(boundary[key] == evidence.get(key), REASON_BOUNDARY,
                     "the boundary claim's %s %r is not what the supervisor "
                     "recorded (%r)" % (key, boundary[key], evidence.get(key)))
    for receipt in receipts:
        summary = receipt.get("boundary") or {}
        _require(summary.get("preflight_sha256") == boundary["preflight_sha256"],
                 REASON_RECEIPT_MISMATCH,
                 "run %s was recorded against different boundary evidence than "
                 "the one the report claims" % receipt.get("run_id"))


def _validate_runs(context_path, claim):
    """Every claimed run must match its supervisor receipt field for field."""
    kinds = set()
    receipts = []
    for entry in claim["runs"]:
        _require(bool(_RECEIPT_ID_RE.match(entry["run_id"])),
                 REASON_RECEIPT_ABSENT,
                 "run_id %r is not the name of a supervisor receipt under "
                 "meta/runs/" % (entry["run_id"],))
        path = os.path.join(context_path, _META_DIR, _RUNS_DIR,
                            "%s.json" % entry["run_id"])
        raw = _read_bytes_or_none(path)
        _require(raw is not None, REASON_RECEIPT_ABSENT,
                 "the report claims run %s but the supervisor has no receipt %s"
                 % (entry["run_id"], path))
        receipt = json.loads(raw.decode("utf-8", "replace"))
        _require(isinstance(receipt, dict)
                 and receipt.get("run_id") == entry["run_id"],
                 REASON_RECEIPT_ABSENT,
                 "receipt %s does not describe run %s"
                 % (path, entry["run_id"]))
        _require(receipt.get("profile") == claim["boundary"]["profile"],
                 REASON_RECEIPT_MISMATCH,
                 "run %s was recorded under profile %r, not the claimed %r"
                 % (entry["run_id"], receipt.get("profile"),
                    claim["boundary"]["profile"]))
        for field in ("kind", "argv", "exit_code", "stdout_sha256",
                      "stderr_sha256", "snapshot_before", "snapshot_after"):
            claimed, recorded = entry[field], receipt.get(field)
            if claimed == recorded:
                continue
            if field == "exit_code" and claimed == 0:
                raise contracts.ContractError(
                    "%s: run %s claims success (exit code 0) while the receipt "
                    "records exit code %s. A truthful failed run stays valid "
                    "evidence; a rewritten status does not"
                    % (REASON_FALSE_SUCCESS, entry["run_id"], recorded))
            raise contracts.ContractError(
                "%s: run %s claims %s=%r while the receipt records %s=%r"
                % (REASON_RECEIPT_MISMATCH, entry["run_id"], field, claimed,
                   field, recorded))
        kinds.add(entry["kind"])
        receipts.append(receipt)
    _require(set(kinds) == set(review_boundary.KINDS), REASON_RUNS,
             "the runs must distinguish a baseline from a probe: claimed %s, "
             "and a guarded publication needs both a baseline acceptance run "
             "and a probe run to be named" % (", ".join(sorted(kinds)) or "none",))
    return receipts


def _named_by_receipts(receipts):
    """{path: set(category)} over every delta any receipt observed."""
    named = {}
    categories = (("modified", "changed_paths"), ("added", "added_paths"),
                  ("removed", "removed_paths"))
    for receipt in receipts:
        for category, field in categories:
            for path in receipt.get(field) or []:
                named.setdefault(path, set()).add(category)
    return named


def _validate_probe_changes(claim, named):
    for change in claim["probe_changes"]:
        path = change["path"]
        _require(path in named, REASON_PROBE_UNNAMED,
                 "no supervisor receipt observed any change to %r, so the probe "
                 "edit has no execution evidence behind it" % (path,))
        if change["deleted"]:
            _require("removed" in named[path], REASON_PROBE_UNNAMED,
                     "the report deletes %r but no receipt removed it" % (path,))
        else:
            _require(bool({"modified", "added"} & named[path]),
                     REASON_PROBE_UNNAMED,
                     "the report edits %r but no receipt modified or added it"
                     % (path,))


def _last_receipt(receipts):
    return max(receipts, key=lambda item: (str(item.get("finished_at")),
                                           str(item.get("run_id"))))


def _validate_residual(claim, receipts):
    """A receipt that says the snapshot still differs may not be erased."""
    last = _last_receipt(receipts)
    categories = (("modified", "changed_paths"), ("added", "added_paths"),
                  ("removed", "removed_paths"))
    for category, field in categories:
        reported = set(claim["residual_changes"][category])
        observed = set(last.get(field) or [])
        missing = sorted(observed - reported)
        _require(not missing, REASON_RESIDUAL,
                 "the report erases the snapshot still differing after run %s: "
                 "residual_changes.%s omits %s (the receipt records %s)"
                 % (last.get("run_id"), category, ", ".join(repr(item)
                                                            for item in missing),
                    ", ".join(repr(item) for item in sorted(observed))))


def _validate_provenance(context_path, manifest, claim, metadata, root):
    """Check the report's claims against the supervisor's own records."""
    context_raw = _read_bytes(os.path.join(context_path, _META_DIR,
                                           _CONTEXT_FILE))
    _require(_sha(context_raw) == claim["context_sha256"], REASON_CONTEXT,
             "the provenance context_sha256 does not cover the bytes of the "
             "supervisor's meta/context.json for this review context")
    _validate_identities(manifest, claim)
    _validate_against_metadata(metadata, claim, root)
    receipts = _validate_runs(context_path, claim)
    _validate_boundary(context_path, claim, receipts)
    _validate_probe_changes(claim, _named_by_receipts(receipts))
    _validate_residual(claim, receipts)


# ---------------------------------------------------------------------------
# Journal recovery
# ---------------------------------------------------------------------------

def _journal_context(context_path):
    manifest = _load_json(os.path.join(context_path, _META_DIR, _CONTEXT_FILE),
                          "the review context manifest")
    live_root = manifest.get("live_root")
    _require(isinstance(live_root, str) and os.path.isdir(live_root),
             REASON_STALE,
             "the review context names no readable live root %r, so a surviving "
             "publication journal cannot be resolved" % (live_root,))
    return manifest, live_root


def _journal_target(live_root, entry):
    rel = entry.get("path")
    if not isinstance(rel, str) or not rel or os.path.isabs(rel) \
            or "\\" in rel or ".." in rel.split("/"):
        raise contracts.ContractError(
            "%s: journal record %r names the unsafe path %r"
            % (REASON_JOURNAL, entry.get("record"), rel))
    return os.path.join(live_root, *rel.split("/"))


def _restore_backup(target, entry):
    """Put one owned record back exactly as it was before the transaction."""
    backup = entry.get("backup_path")
    if entry.get("old_sha256") is None:
        # The record did not exist before: ownership means removing what was
        # created, never writing an empty file over a person's record.
        _remove_file(target)
        return
    if not isinstance(backup, str) or not os.path.isfile(backup):
        raise contracts.ContractError(
            "%s: the journal entry for %r has no readable backup of the original "
            "bytes, so the interrupted write cannot be undone; resolve it by hand"
            % (REASON_JOURNAL, entry.get("record")))
    _write_bytes(target, _read_bytes(backup))


def _recover_journal(path, manifest, live_root):
    """Recover one journal's owned writes; block if it cannot be undone."""
    payload = _load_json(path, "a publication journal")
    _require(payload.get("format_version") == JOURNAL_FORMAT_VERSION,
             REASON_JOURNAL,
             "%s is not a format_version %d publication journal"
             % (path, JOURNAL_FORMAT_VERSION))
    _require(payload.get("ticket_id") == manifest.get("ticket_id")
             and payload.get("reviewed_commit") == manifest.get("reviewed_commit"),
             REASON_JOURNAL,
             "%s belongs to ticket %r at %s, not to this review context; a "
             "journal from another context or publisher is never rewritten here"
             % (path, payload.get("ticket_id"), payload.get("reviewed_commit")))
    blocked = []
    for entry in payload.get("records") or []:
        target = _journal_target(live_root, entry)
        current = _sha_or_none(_read_bytes_or_none(target))
        if current is None and entry.get("old_sha256") is None:
            continue  # never written, or already back where it was
        if current == entry.get("old_sha256"):
            continue  # already the original bytes
        if current != entry.get("owned_sha256"):
            # Somebody else wrote this record. Their bytes stay theirs.
            blocked.append((entry.get("record"), target))
    for entry in payload.get("records") or []:
        target = _journal_target(live_root, entry)
        current = _sha_or_none(_read_bytes_or_none(target))
        if current == entry.get("owned_sha256"):
            _restore_backup(target, entry)
    if blocked:
        raise contracts.ContractError(
            "%s: %s holds a write to %s that this transaction does not own, so "
            "the unfinished journal %s cannot be recovered and this context is "
            "blocked for reuse until the records are reconciled by hand"
            % (REASON_JOURNAL, path,
               ", ".join(repr(name) for name, _ in blocked), path))
    _retire_journal(path)
    return os.path.realpath(path)


def _retire_journal(path):
    directory = os.path.dirname(path)
    try:
        if os.path.isfile(os.path.join(directory, _RECORD_FILE)):
            # The transaction committed; only the journal goes.
            os.remove(path)
            return
        shutil.rmtree(directory)
    except OSError as exc:
        raise contracts.ContractError(
            "cannot retire the publication journal %r: %s" % (path, exc))


def _recover_stray_journals_locked(context_path):
    manifest, live_root = _journal_context(context_path)
    recovered = []
    for path in _journal_entries(context_path):
        recovered.append(_recover_journal(path, manifest, live_root))
    return recovered


def recover_stray_journals(context_path):
    """Recover every unfinished publication journal for this context.

    Called before any new publication, and safe to call from a coordinator
    directly: a file still holding the interrupted transaction's own bytes is
    restored byte-exactly, and anything a foreign writer touched is left alone —
    in which case the journal survives and publication stays blocked. Returns the
    paths of the journals that were cleared.
    """
    manifest, _root = _journal_context(context_path)
    with _Lock(context_path, manifest.get("ticket_id")):
        return _recover_stray_journals_locked(context_path)


# ---------------------------------------------------------------------------
# The transaction
# ---------------------------------------------------------------------------

def _write_journal(path, ticket_id, manifest, entries):
    payload = {
        "format_version": JOURNAL_FORMAT_VERSION,
        "ticket_id": ticket_id,
        "reviewed_commit": manifest.get("reviewed_commit"),
        "created_at": _now(),
        "records": entries,
    }
    _write_bytes(path, json.dumps(payload, indent=2, sort_keys=True)
                 .encode("utf-8"))


def _owned_temp(target, txn, payload):
    """One unique adjacent temporary file holding exactly the new bytes."""
    temp = target + _TEMP_FORMAT % txn
    _write_bytes(temp, payload)
    return temp


def _discard_temps(temps):
    """Remove this transaction's own adjacent temporary files, best effort.

    A stray temporary inside the Ticket work directory would read as untracked
    drift to the next currentness check, so an abandoned transaction never leaves
    one behind.
    """
    for temp in temps:
        try:
            _remove_file(temp)
        except contracts.ContractError:
            pass  # a stray private temporary is noise next to a lost record


def _recover_entries(entries, temps, live_root):
    """Restore only records still holding this transaction's bytes.

    Returns the records another writer reached, which are never touched.
    """
    foreign = []
    for entry in entries:
        target = _journal_target(live_root, entry)
        current = _sha_or_none(_read_bytes_or_none(target))
        if current == entry["owned_sha256"]:
            _restore_backup(target, entry)
        elif current != entry["old_sha256"]:
            foreign.append((entry["record"], target))
    _discard_temps(temps)
    return foreign


def _publish(root, ticket_id, context_path, manifest, payloads, records,
             verdict, live_head, claim):
    """Replace Handoff, then Review, then State, journaling every step.

    Handoff and Review go first and State last: State is the binding commit
    marker, so a transaction that never reached State provably published nothing,
    and its journal can be rolled back. A surviving journal therefore always means
    an uncommitted transaction — the journal is retired the moment State lands.
    """
    txn = uuid.uuid4().hex
    directory = os.path.join(_publication_dir(context_path), txn)
    backup_dir = os.path.join(directory, _BACKUP_DIR)
    journal_path = os.path.join(directory, _JOURNAL_FILE)
    try:
        os.makedirs(backup_dir)
    except OSError as exc:
        raise contracts.ContractError("cannot create %r: %s" % (directory, exc))

    entries = []
    temps = []
    replaced = []
    staged = os.path.join(directory, "state.staged.yaml")
    try:
        _stage_state(staged, copy.deepcopy(payloads["state"]))
        payloads["state"] = _read_bytes(staged)
        for record in _RECORD_ORDER:
            rel, target = records[record]
            original = _read_bytes_or_none(target)
            backup = os.path.join(backup_dir, "%s.original" % record)
            if original is not None:
                _write_bytes(backup, original)
            entries.append({
                "record": record,
                "path": rel,
                "old_sha256": _sha_or_none(original),
                "owned_sha256": _sha(payloads[record]),
                "backup_path": backup if original is not None else None,
            })
        _write_journal(journal_path, ticket_id, manifest, entries)
        owned = {entry["record"]: entry["owned_sha256"] for entry in entries}

        for entry in entries:
            temps.append(_owned_temp(records[entry["record"]][1], txn,
                                     payloads[entry["record"]]))
        for entry in entries:
            record = entry["record"]
            _replace(records[record][1] + _TEMP_FORMAT % txn,
                     records[record][1])
            replaced.append(record)

        # State landed: this transaction is committed, so it is no longer an
        # unfinished journal. Nothing after this point may roll it back.
        os.remove(journal_path)
        shutil.rmtree(backup_dir)

        # Recheck the live identities: a conflict is reported, never repaired.
        conflict = [entry["record"] for entry in entries
                    if _sha_or_none(_read_bytes_or_none(
                        records[entry["record"]][1])) != owned[entry["record"]]]
        _write_bytes(os.path.join(directory, _RECORD_FILE),
                     json.dumps(_record_payload(ticket_id, manifest, verdict,
                                                 live_head, entries, claim,
                                                 conflict),
                                indent=2, sort_keys=True).encode("utf-8"))
        if conflict:
            raise contracts.ContractError(
                "%s: the publication completed but %s no longer holds this "
                "transaction's bytes — another writer reached the same records. "
                "The verdict is recorded and the binding is now stale; the review "
                "must be re-taken, not silently refreshed"
                % (REASON_CONFLICT, ", ".join(repr(name) for name in conflict)))
    except contracts.ContractError as exc:
        if not replaced:
            _discard_temps(temps)
            shutil.rmtree(directory, ignore_errors=True)
            raise
        foreign = _recover_entries(entries, temps, root)
        if foreign:
            raise contracts.ContractError(
                "%s: the transaction failed (%s) and could not undo its own "
                "writes because %s now holds bytes this publisher never owned; "
                "the journal %s stays and blocks this context until the records "
                "are reconciled"
                % (REASON_JOURNAL, exc,
                   ", ".join(repr(name) for name, _ in foreign), journal_path)
            ) from exc
        shutil.rmtree(directory, ignore_errors=True)
        raise
    except OSError as exc:
        if not replaced:
            _discard_temps(temps)
            shutil.rmtree(directory, ignore_errors=True)
            raise contracts.ContractError("%s: %s" % (REASON_WRITE, exc)) from exc
        foreign = _recover_entries(entries, temps, root)
        if foreign:
            # The journal and its backups stay exactly where they are: a later
            # publisher must recover them or be blocked, never lose the evidence.
            raise contracts.ContractError(
                "%s: the transaction failed (%s) and could not undo its own "
                "writes because %s now holds bytes this publisher never owned; "
                "the journal %s stays and blocks this context until the records "
                "are reconciled"
                % (REASON_JOURNAL, exc,
                   ", ".join(repr(name) for name, _ in foreign), journal_path)
            ) from exc
        shutil.rmtree(directory, ignore_errors=True)
        raise contracts.ContractError("%s: %s" % (REASON_WRITE, exc)) from exc
    return owned


def _record_payload(ticket_id, manifest, verdict, live_head, entries, claim,
                    conflict):
    return {
        "format_version": RECORD_FORMAT_VERSION,
        "ticket_id": ticket_id,
        "reviewed_commit": manifest.get("reviewed_commit"),
        "live_head": live_head,
        "verdict": verdict,
        "created_at": _now(),
        "profile": review_boundary.PROFILE,
        "context_sha256": claim["context_sha256"],
        "preflight_sha256": claim["boundary"]["preflight_sha256"],
        "records": [{"record": entry["record"], "path": entry["path"],
                     "old_sha256": entry["old_sha256"],
                     "published_sha256": entry["owned_sha256"]}
                    for entry in entries],
        "conflict": list(conflict),
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _decode_text(raw, what):
    """Decode a candidate payload's bytes as UTF-8 text, naming the payload."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise contracts.ContractError("%s is not UTF-8 text: %s" % (what, exc))


def publish(root, ticket_id, context_path, report_raw, handoff_raw,
            proposed_state):
    """Validate and publish one isolated review candidate; write nothing else.

    Every check — the candidate's own consistency, the reserved provenance
    section against the supervisor's receipts, the review context's currentness,
    the HARDEN-010 code drift and each captured input hash — runs before a single
    live record is touched, and a mismatch performs zero live writes. The caller
    supplies the Reviewer's verdict inside `proposed_state`; this function never
    synthesizes one, never repairs source and never transitions a phase.

    Raises `contracts.ContractError` for every refusal, naming what was missing.
    """
    for name, payload in (("report_raw", report_raw), ("handoff_raw", handoff_raw)):
        if not isinstance(payload, (bytes, bytearray)):
            raise contracts.ContractError(
                "%s must be the candidate's raw bytes, got %s"
                % (name, type(payload).__name__))
    report_raw = bytes(report_raw)
    handoff_raw = bytes(handoff_raw)
    if not isinstance(proposed_state, dict):
        raise contracts.ContractError(
            "proposed_state must be the proposed State map, got %s"
            % type(proposed_state).__name__)

    state_path = os.path.join(root, ".ai", "work", ticket_id, "state.yaml")
    try:
        live = state.load_file(state_path)
    except (state.StateError, OSError) as exc:
        raise contracts.ContractError("cannot read the live State: %s" % exc)

    verdict, block = _candidate_verdict(proposed_state)
    _require_only_verdict_change(live, proposed_state)

    report = contracts.parse_artifact(report_raw, "review")
    problems = contracts.validate_review(report, ticket_id, verdict)
    _require(not problems, "candidate-review-invalid",
             "the candidate Review is structurally invalid: %s"
             % "; ".join(problems))
    handoff_problems = contracts.validate_handoff(_decode_text(
        handoff_raw, "the candidate Handoff"))
    _require(not handoff_problems, REASON_HANDOFF,
             "the candidate Handoff is not ready for the retained review phase: "
             "%s" % "; ".join(handoff_problems))

    claim = contracts.read_review_provenance(report_raw)
    _require(claim is not None, "provenance-absent",
             "the candidate Review declares no `## Isolation provenance` "
             "section, so it claims no isolation run; a guarded publication "
             "against a review context never invents that evidence afterwards")
    _require_binding(verdict, block, report_raw, claim)

    # Recheck currentness, then the report's claims, before anything is written.
    manifest = review_snapshot.assert_current(root, ticket_id, context_path)
    _validate_provenance(context_path, manifest, claim,
                         report.get("metadata") or {}, root)
    plan_path = (manifest.get("plan") or {}).get("path") or ""
    drift = review.code_drift(root, ticket_id, manifest["reviewed_commit"],
                              plan_path)
    _require(not drift, REASON_STALE,
             "the reviewed code changed since %s, so this candidate may not be "
             "published over it: %s" % (manifest["reviewed_commit"],
                                        "; ".join(drift)))
    live_head_value = live_head(root)
    records = _record_paths(root, ticket_id, proposed_state)
    # The State payload starts as the proposed map; the transaction stages it
    # privately through `state.save_file` and publishes exactly those bytes.
    payloads = {"handoff": handoff_raw, "review": report_raw,
                "state": proposed_state}

    with _Lock(context_path, ticket_id):
        _recover_stray_journals_locked(context_path)
        # Coordinator-exclusive publication: the live records must still be the
        # ones this context captured, with nothing half-written by anybody else.
        _require_current_records(state_path, records, manifest, report_raw)
        _publish(root, ticket_id, context_path, manifest, payloads, records,
                 verdict, live_head_value, claim)


def _require_current_records(state_path, records, manifest, report_raw):
    """Re-read the old record identities inside the lock."""
    state_raw = _read_bytes_or_none(state_path)
    _require(state_raw is not None, REASON_STALE,
             "the live State disappeared before publication")
    captured = manifest.get("inputs") or {}
    state_rel = records["state"][0]
    _require(_sha(state_raw) == captured.get(state_rel), REASON_STALE,
             "the live State no longer matches the identity captured with this "
             "review context, so another context or writer reached it")
    handoff_raw = _read_bytes_or_none(records["handoff"][1])
    _require(_sha_or_none(handoff_raw)
             == captured.get(records["handoff"][0]), REASON_STALE,
             "the live Handoff no longer matches the identity captured with this "
             "review context, so another context or writer reached it")
    review_raw = _read_bytes_or_none(records["review"][1])
    _require(review_raw is None or _sha(review_raw) != _sha(report_raw),
             REASON_STALE,
             "the live Review already holds these exact candidate bytes, so this "
             "publication has nothing left to publish; re-read the records "
             "instead of publishing the same verdict twice")
