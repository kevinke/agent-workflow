"""state.yaml load/save on top of the restricted YAML parser.

Unknown fields are preserved on load and save; they are never an error and are
never deleted (STATE_SCHEMA.md). Every save stamps `updated_at` with the current
ISO-8601 timestamp.
"""

import datetime
import os

import parser

__all__ = ["load_file", "save_file", "StateError"]


class StateError(Exception):
    """Raised for state.yaml IO or parse problems."""


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def load_file(path):
    """Load a state.yaml into a dict. Raises StateError on parse failure."""
    if not os.path.exists(path):
        raise StateError("state.yaml not found: %s" % path)
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        data = parser.parse(text)
    except parser.YAMLParseError as exc:
        raise StateError("invalid state.yaml (%s): %s" % (path, exc))
    if not isinstance(data, dict):
        raise StateError("state.yaml root must be a map: %s" % path)
    return data


def save_file(path, data):
    """Serialize data back, stamp updated_at, and write atomically."""
    if not isinstance(data, dict):
        raise StateError("state root must be a map")
    data["updated_at"] = _now_iso()
    text = parser.dump(data)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)