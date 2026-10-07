"""Workflow version selection and shared v2 policy helpers (SCOUT-002).

Pure functions only: this module never writes and never imports mutate or
validate (the common plan's dependency order). `version` decides whether a
ticket's State follows v1 semantics or the stricter v2 contracts;
`problems` reports shared v2 State-shape problems as strings so `validate`
can convert them into ERROR Findings.
"""

import contracts

__all__ = ["version", "problems", "SUPPORTED_VERSIONS"]

SUPPORTED_VERSIONS = (1, 2)


def version(data):
    """Return the ticket's workflow version: missing means 1.

    Only integer 1/2 are accepted; bools, zero, strings, and future versions
    raise ContractError so unsupported versions fail clearly instead of
    silently falling back to v1 rules.
    """
    if not isinstance(data, dict):
        raise contracts.ContractError("state root must be a map")
    ver = data.get("workflow_version", 1)
    if ver is None:
        ver = 1
    if isinstance(ver, bool) or not isinstance(ver, int) or ver not in SUPPORTED_VERSIONS:
        raise contracts.ContractError(
            "unsupported workflow_version %r (must be one of %s)"
            % (ver, ", ".join(str(v) for v in SUPPORTED_VERSIONS)))
    return ver


def _is_int(value):
    return not isinstance(value, bool) and isinstance(value, int)


def problems(root, data):
    """Shared v2 State-shape problems; [] means the State shape is fine.

    Read-only by contract. Version violations are reported as a problem
    string here (not raised) so `validate` can surface them as Findings
    without crashing the rest of the validation pass.
    """
    try:
        ver = version(data)
    except contracts.ContractError as exc:
        return [str(exc)]

    out = []
    if ver != 2:
        return out

    evidence = data.get("evidence") or {}
    for key in ("report_sha256", "audit_sha256"):
        if key in evidence and evidence[key] is not None \
                and not isinstance(evidence[key], str):
            out.append("evidence.%s must be a string or null" % key)

    implementation = data.get("implementation") or {}
    if "task_hashes" in implementation \
            and not isinstance(implementation["task_hashes"], list):
        out.append("implementation.task_hashes must be a list")
    if "current_task" in implementation and implementation["current_task"] is not None \
            and not _is_int(implementation["current_task"]):
        out.append("implementation.current_task must be an integer")

    review = data.get("review") or {}
    if "verdict" in review and review["verdict"] is not None \
            and review["verdict"] not in ("pending", "pass", "changes_requested"):
        out.append("review.verdict must be pending|pass|changes_requested")

    upgrade = data.get("upgrade") or {}
    if "from_version" in upgrade and upgrade["from_version"] is not None \
            and not _is_int(upgrade["from_version"]):
        out.append("upgrade.from_version must be an integer")

    return out
