"""Read-only Git transport assessment for raw-byte work artifacts (HARDEN-006).

`ai-workflow` binds work artifacts (Evidence, Audit, Review, the registered
Plan) by SHA-256 over their RAW bytes. On a fresh clone or checkout, Git's
`text` attribute (and the core.autocrlf normalization it defers to) can
rewrite those bytes and silently invalidate every binding. This module reports
which paths carry an effective `text` attribute other than unset (`-text`) so
a human can pin them explicitly.

Strictly read-only and single-purpose:

- the only Git call is `git --no-optional-locks check-attr -z text -- <paths>`
  (`--no-optional-locks` keeps the index stat cache untouched, as in
  `validate._git_dirty`); it never writes the index, any config, or a file;
- it never edits repository-root attributes or the global configuration, and
  never renormalizes tracked files — adding a per-path `-text` rule is always
  the user's explicit decision;
- it never raises: an unavailable git, a non-repository root, or a check-attr
  failure comes back as no warnings ([]) — the same degraded-read convention
  as the other read-only Git observers — because a transport notice must
  never become a new execution gate.
"""

import subprocess

__all__ = ["attribute_problems", "SAFE_TEXT_VALUE"]

# The only effective `text` value that guarantees byte-stable checkouts is an
# explicit unset. `set`, `text=auto`, and an unspecified attribute (which
# defers to core.autocrlf) can all rewrite raw bytes in transit.
SAFE_TEXT_VALUE = "unset"


def _warning(path, value):
    if value == "unspecified":
        detail = "no explicit text attribute (core.autocrlf decides)"
    else:
        detail = "text attribute %r" % value
    return ("transport: %s: %s; raw-byte artifact bindings may not survive a "
            "clone/checkout (pin the path with a '-text' attribute)"
            % (path, detail))


def attribute_problems(root, paths):
    """Warnings for paths whose effective `text` attribute is not unset.

    `paths` are repository-relative paths (as recorded in State, e.g. the
    registered Plan reference). Returns a list of human-readable warning
    strings, one per unprotected path, in input order without duplicates;
    [] means every given path is either explicitly `-text` or Git could not
    be asked (never an exception). Failures degrade to no warnings so the
    notices stay visible-only and never gate execution.
    """
    ordered = []
    for path in paths or []:
        if not path:
            continue
        clean = str(path).replace("\\", "/")
        if clean not in ordered:
            ordered.append(clean)
    if not ordered:
        return []
    try:
        proc = subprocess.run(
            ["git", "--no-optional-locks", "-C", root, "check-attr", "-z",
             "text", "--"] + ordered,
            capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return []  # no Git to ask: degraded read, never a gate, never a raise
    if proc.returncode != 0:
        return []
    problems = []
    fields = proc.stdout.decode("utf-8", "surrogateescape").split("\0")
    # NUL-delimited triples: <path> NUL <attribute> NUL <value> NUL, repeated.
    for i in range(0, len(fields) - 2, 3):
        path, _attribute, value = fields[i], fields[i + 1], fields[i + 2]
        if not path or value == SAFE_TEXT_VALUE:
            continue
        problems.append(_warning(path, value))
    return problems
