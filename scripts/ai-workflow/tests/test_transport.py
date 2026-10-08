"""Tests for bounded Git attribute protection and transport notices (HARDEN-006).

`ai-workflow` binds work artifacts (Evidence, Audit, Review, the registered
Plan) by SHA-256 over RAW bytes. Git text-attribute normalization on a fresh
clone or checkout can rewrite those bytes and invalidate every binding. These
tests pin the protection contract:

- `init` installs a single-purpose `.ai/work/.gitattributes` (`** -text`)
  only when absent, byte-stable across repeated init;
- with local autocrlf true and false, protected raw bytes survive
  commit -> clone unchanged;
- a user's existing custom work attribute file is preserved byte-identically,
  and effective `text` conflicts (`text=auto`, `set`, unspecified) are warned
  about by the read-only `transport.attribute_problems`;
- a transport warning is never a new execution gate: v2 validation stays
  error-free while the warning is visible in validate and resume.
"""

import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import init  # noqa: E402
import resume as resume_module  # noqa: E402
import transport  # noqa: E402
import validate  # noqa: E402
from v2_support import V2CLITestCase, valid_plan  # noqa: E402

# Mixed line endings everywhere: only a `-text` transport guarantee keeps
# these bytes stable across a checkout.
MIXED_WORK = b"# work artifact\r\nLF line\nCRLF line\r\ntrailing LF\n"
MIXED_TASK = b"# work plan\nLF line\r\nCRLF line\r\ntrailing LF\n"
MIXED_PLAN = b"# external plan\r\nLF line\nCRLF line\ntrailing LF\n"

# A custom user attribute file: the broader `** -text` baseline with a
# more-specific `*.md` override that reintroduces normalization risk.
CUSTOM_ATTRIBUTES = b"** -text\n*.md text=auto\n"


def _git(root, *args):
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": "transport-fixture",
        "GIT_AUTHOR_EMAIL": "transport-fixture@local",
        "GIT_COMMITTER_NAME": "transport-fixture",
        "GIT_COMMITTER_EMAIL": "transport-fixture@local",
    })
    return subprocess.run(["git", "-C", root] + list(args),
                          capture_output=True, text=True, env=env)


def _new_repo(autocrlf=None):
    """A disposable Git repository with an optional LOCAL autocrlf override."""
    tmp = tempfile.TemporaryDirectory()
    root = tmp.name
    _git(root, "init", "-q")
    if autocrlf is not None:
        _git(root, "config", "core.autocrlf", autocrlf)
    return tmp, root


def _write(root, rel, data):
    """Write raw bytes at repo-relative `rel` (creating directories)."""
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def _read(root, rel):
    with open(os.path.join(root, rel), "rb") as fh:
        return fh.read()


def _commit_all(root, message="fixture: raw artifacts"):
    added = _git(root, "add", "-A")
    assert added.returncode == 0, added.stderr
    commit = _git(root, "commit", "-q", "-m", message)
    assert commit.returncode == 0, commit.stderr


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


class NewWorkAttributesTest(unittest.TestCase):
    """The installed work attributes and raw bytes across a clone."""

    def test_new_work_attributes_keep_bytes_across_checkout(self):
        for autocrlf in ("true", "false"):
            with self.subTest(autocrlf=autocrlf):
                tmp, root = _new_repo(autocrlf)
                self.addCleanup(tmp.cleanup)
                init.init(root)

                installed_attributes = Path(root, ".ai", "work", ".gitattributes")
                self.assertTrue(installed_attributes.exists())
                self.assertEqual(installed_attributes.read_bytes(), b"** -text\n")

                # Work artifacts (protected by the installed file) plus an
                # external Plan outside .ai/work/ carrying an explicit root
                # per-path -text rule (the manual external-Plan rule).
                rels = (".ai/work/T1/evidence.md",
                        ".ai/work/T1/plan.md",
                        "docs/external-plan.md")
                _write(root, rels[0], MIXED_WORK)
                _write(root, rels[1], MIXED_TASK)
                _write(root, rels[2], MIXED_PLAN)
                _write(root, ".gitattributes",
                       b"docs/external-plan.md -text\n")
                _commit_all(root)

                original_bytes = tuple(_read(root, rel) for rel in rels)
                self.assertEqual(len(set(map(_sha256, original_bytes))), 3)

                clone_tmp = tempfile.TemporaryDirectory()
                self.addCleanup(clone_tmp.cleanup)
                clone = os.path.join(clone_tmp.name, "clone")
                cloned = _git(root, "clone", "-q", ".", clone)
                self.assertEqual(cloned.returncode, 0, cloned.stderr)

                after_clone_bytes = tuple(_read(clone, rel) for rel in rels)
                self.assertEqual(after_clone_bytes, original_bytes)
                # The protection itself travels with the clone.
                self.assertEqual(
                    Path(clone, ".ai", "work", ".gitattributes").read_bytes(),
                    b"** -text\n")


class ExistingAttributesTest(unittest.TestCase):
    """Existing user attributes are preserved; conflicts are warned."""

    def test_existing_attributes_preserved_and_conflicts_warn(self):
        tmp, root = _new_repo("false")
        self.addCleanup(tmp.cleanup)
        init.init(root)

        existing_attributes = Path(root, ".ai", "work", ".gitattributes")
        before_attributes = CUSTOM_ATTRIBUTES
        existing_attributes.write_bytes(before_attributes)

        # A work-dir artifact whose effective text attribute is text=auto via
        # the more-specific *.md override; a binary work file stays -text.
        _write(root, ".ai/work/T1/evidence.md", MIXED_WORK)
        _write(root, ".ai/work/T1/data.bin", b"\x00\x01binary\r\n")
        # An unprotected external Plan (no attribute rule reaches it) beside a
        # protected one (explicit root per-path -text rule).
        unprotected_plan = "docs/unprotected-plan.md"
        _write(root, unprotected_plan, MIXED_PLAN)
        _write(root, "docs/protected-plan.md", MIXED_PLAN)
        _write(root, ".gitattributes", b"docs/protected-plan.md -text\n")
        _commit_all(root)

        # Repeated init preserves the user's custom attribute file
        # byte-identically (never reinstalls the template over it).
        created = init.init(root)
        self.assertNotIn(str(existing_attributes), created)
        self.assertEqual(existing_attributes.read_bytes(), before_attributes)

        # transport must stay read-only: the real index's bytes AND mtime.
        index_path = Path(root, ".git", "index")
        before_index = index_path.read_bytes()
        before_mtime = os.stat(index_path).st_mtime

        problems = transport.attribute_problems(
            root, [unprotected_plan, "docs/protected-plan.md",
                   ".ai/work/T1/evidence.md", ".ai/work/T1/data.bin"])
        joined = "\n".join(problems)
        self.assertTrue(transport.attribute_problems(root, [unprotected_plan]))
        self.assertIn(unprotected_plan, joined)          # unspecified -> warn
        self.assertIn(".ai/work/T1/evidence.md", joined)  # text=auto -> warn
        self.assertNotIn("docs/protected-plan.md", joined)
        self.assertNotIn(".ai/work/T1/data.bin", joined)

        self.assertEqual(index_path.read_bytes(), before_index)
        self.assertEqual(os.stat(index_path).st_mtime, before_mtime)


class InitStabilityTest(unittest.TestCase):
    """Repeated init is byte-stable; the template is exact."""

    def test_repeated_init_keeps_installed_attributes_byte_stable(self):
        tmp, root = _new_repo("false")
        self.addCleanup(tmp.cleanup)
        init.init(root)
        attrs = Path(root, ".ai", "work", ".gitattributes")
        first = attrs.read_bytes()
        self.assertEqual(first, b"** -text\n")
        created = init.init(root)
        self.assertNotIn(str(attrs), created)
        self.assertEqual(attrs.read_bytes(), first)


class AttributeConflictsTest(unittest.TestCase):
    """Every effective text value other than unset warns; unset never does."""

    def test_auto_set_and_unspecified_conflicts_warn(self):
        tmp, root = _new_repo("false")
        self.addCleanup(tmp.cleanup)
        init.init(root)
        _write(root, ".gitattributes",
               b"auto.txt text=auto\n"
               b"set.txt text\n"
               b"unset.txt -text\n")
        problems = transport.attribute_problems(
            root, ["auto.txt", "set.txt", "unset.txt", "unspecified.txt"])
        self.assertEqual(len(problems), 3, problems)
        joined = "\n".join(problems)
        for warned in ("auto.txt", "set.txt", "unspecified.txt"):
            self.assertIn(warned, joined)
        self.assertNotIn("unset.txt", joined)

    def test_spaces_in_plan_paths_are_assessed(self):
        tmp, root = _new_repo("false")
        self.addCleanup(tmp.cleanup)
        init.init(root)
        _write(root, "docs/outer plan.md", MIXED_PLAN)
        spaced = "docs/outer plan.md"
        self.assertTrue(transport.attribute_problems(root, [spaced]))
        # A literal gitattributes pattern cannot contain an embedded space
        # (patterns split on whitespace); a glob pins the spaced path.
        _write(root, ".gitattributes", b"docs/*.md -text\n")
        self.assertEqual(transport.attribute_problems(root, [spaced]), [])


class TransportNoticeV2Test(V2CLITestCase):
    """A transport warning is visible but never a new v2 execution gate."""

    def test_transport_warning_is_not_a_v2_gate(self):
        # Bind the Evidence/Audit bytes (sufficient gate) and register an
        # external Plan outside .ai/work/ -- left unprotected on purpose.
        self.seed_v2("evidence_audit")
        self.write_evidence(round_no=1)
        self.write_audit(gate="sufficient", round_no=1)
        proc = self.cli("set-gate", self.TICKET, "--gate", "sufficient",
                        "--round", "1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = self.cli("advance", self.TICKET, "--to", "technical_decision")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = self.cli("advance", self.TICKET, "--to", "planning")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.write_decision()
        _write(self.root, "docs/outer plan.md",
               valid_plan(self.TICKET, 1).encode("utf-8"))
        proc = self.cli("register-plan", self.TICKET, "--path",
                        "docs/outer plan.md", "--total", "1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        # A broad root rule that reaches the bound Plan. The deeper
        # .ai/work/.gitattributes still protects the work-dir artifacts.
        _write(self.root, ".gitattributes", b"* text=auto\n")

        findings = []
        validate.validate_ticket(self.root, self.TICKET, findings)
        errors = [f for f in findings if f.severity == "ERROR"]
        warnings = [f for f in findings if f.severity == "WARN"
                    and "outer plan.md" in f.message]
        self.assertEqual(errors, [])
        self.assertTrue(warnings, findings)

        # The same read-only notice surfaces in the resume brief without
        # blocking continuation (warnings are never an execution gate).
        brief = resume_module.resume_for_ticket(self.root, self.TICKET)
        self.assertIn("outer plan.md", brief)
        self.assertFalse(resume_module.continuation_blocked(self.root,
                                                            self.TICKET))


if __name__ == "__main__":
    unittest.main()
