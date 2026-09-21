"""Restricted YAML subset parser (ADR-0002).

Parses only the constructs used by the fixed state.yaml schema: block-style
nested maps, block-style dash lists, an empty litertal sequence `[]`, and
scalars (plain or quoted strings, integers, booleans, null). Anything outside
the subset raises YAMLParseError. There is no PyYAML dependency.

Rejected (validate must surface these as errors): anchors and aliases (`&`,
`*`), tags (`!`), flow-style collections, multi-line block scalars (`|`, `>`),
multi-document streams (`---`, `...`).
"""

import re

__all__ = ["parse", "dump", "YAMLParseError"]


class YAMLParseError(Exception):
    """Raised when the input uses constructs outside the restricted subset."""


_LEADING_SPACE_RE = re.compile(r"^( *)(.*)$")
# A map entry line:  key: value   (key must not start with a dash-item or quote
# within the line, and must contain a colon followed by space/end/colon).
_KEY_VALUE_RE = re.compile(r"^(.*?):[ \t]*(.*)$")


def _strip_offset(content, indent):
    """Verify forbidden constructs that can appear in the middle of a line."""
    stripped = content.strip()
    # multi-line block scalars and document markers are handled at line level.
    if stripped.startswith(("|", ">")) and (len(stripped) == 1 or stripped[1] == " "):
        raise YAMLParseError("block scalar literal (| or >) not in subset")
    if re.search(r"[&*!]", stripped):
        raise YAMLParseError(
            "forbidden YAML construct: & (anchor), * (alias), or ! (tag): %r" % stripped
        )
    return stripped


def _split_comment(content):
    """Split off a trailing `# comment` that is outside any quotes."""
    in_single = False
    in_double = False
    for i, ch in enumerate(content):
        if ch == "'":
            in_single = not in_single
        elif ch == '"':
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            if i == 0 or content[i - 1] in " \t":
                return content[:i]
    return content


def _parse_scalar(raw):
    """Convert a trimmed scalar token to a Python value."""
    if raw in ("", "null", "Null", "NULL", "~"):
        return None
    if raw == "[]":
        return []
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        body = raw[1:-1]
        return body.replace('\\"', '"').replace("\\\\", "\\")
    if raw.startswith("'") and raw.endswith("'") and len(raw) >= 2:
        return raw[1:-1].replace("''", "'")
    if raw in ("true", "True", "TRUE"):
        return True
    if raw in ("false", "False", "FALSE"):
        return False
    if re.fullmatch(r"-?[0-9]+", raw):
        return int(raw)
    return raw


def _detect_inline(value_part):
    """Classify an inline value partner: scalars and the literal empty list."""
    stripped = value_part.strip()
    if stripped == "[]":
        return []
    if stripped.startswith(("|", ">")) and (len(stripped) == 1 or stripped[1] == " "):
        raise YAMLParseError("block scalar literal (| or >) not in subset: %r" % value_part)
    if _is_flowlike(stripped) or stripped in ("[", "]", "{", "}"):
        raise YAMLParseError("flow-style collection not in subset: %r" % value_part)
    return _parse_scalar(value_part)


def _is_flowlike(s):
    stripped = s.strip()
    return any(c in stripped for c in "{},[")


class _Index:
    __slots__ = ("i",)

    def __init__(self, i=0):
        self.i = i


def _build(entries, idx, indent):
    """Build a node from entries starting at idx with the given base indent."""
    if idx.i >= len(entries):
        return None
    base_indent, content = entries[idx.i]
    if base_indent != indent:
        return None
    token = content.strip()
    if token.startswith("-"):
        return _build_list(entries, idx, indent)
    return _build_map(entries, idx, indent)


def _build_map(entries, idx, indent):
    node = {}
    while idx.i < len(entries):
        cur_indent, content = entries[idx.i]
        if cur_indent != indent:
            break
        raw = _strip_offset(content, cur_indent)
        if raw.startswith("-"):
            raise YAMLParseError("sequence dash in the middle of a map (line %d)" % (idx.i + 1))
        m = _KEY_VALUE_RE.match(raw)
        if not m:
            raise YAMLParseError("expected 'key: value', got %r (line %d)" % (raw, idx.i + 1))
        key = m.group(1).strip()
        if not key or key in ("&", "*", "!"):
            raise YAMLParseError("invalid key %r (line %d)" % (key, idx.i + 1))
        key = key.strip('"').strip("'")
        value_part = m.group(2).strip()
        if value_part == "":
            # Value is either an inline nothing (null) or a nested block on the
            # next line at greater indent.
            if idx.i + 1 < len(entries) and entries[idx.i + 1][0] > indent:
                idx.i += 1
                node[key] = _build(entries, idx, entries[idx.i][0])
            else:
                node[key] = None
                idx.i += 1
        else:
            node[key] = _detect_inline(value_part)
            idx.i += 1
    return node


def _build_list(entries, idx, indent):
    node = []
    while idx.i < len(entries):
        cur_indent, content = entries[idx.i]
        if cur_indent != indent:
            break
        raw = _strip_offset(content, cur_indent)
        if not raw.startswith("-"):
            raise YAMLParseError("map entry in the middle of a sequence (line %d)" % (idx.i + 1))
        item_rest = raw[1:].strip()
        if item_rest == "":
            # Nested block item.
            if idx.i + 1 < len(entries) and entries[idx.i + 1][0] > indent:
                idx.i += 1
                node.append(_build(entries, idx, entries[idx.i][0]))
            else:
                node.append(None)
                idx.i += 1
        elif _KEY_VALUE_RE.match(item_rest) and not _is_flowlike(item_rest):
            # On-line map entry inside a sequence, e.g. `- key: value`.
            node.append(_build_map([(indent, item_rest)], _Index(0), indent))
            idx.i += 1
        else:
            node.append(_detect_inline(item_rest))
            idx.i += 1
    return node


def parse(text):
    """Parse a restricted-YAML document into a dict/list/scalar structure."""
    # Guard against multi-document or block-scalar beginnings anywhere (cheap).
    for bad in ("---", "..."):
        if bad in text:
            raise YAMLParseError("multi-document stream marker %r not in subset" % bad)

    entries = []
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.rstrip("\n")
        if not line.strip():
            continue
        m = _LEADING_SPACE_RE.match(line)
        indent = len(m.group(1))
        content = _split_comment(m.group(2))
        stripped = _strip_offset(content, indent)
        if stripped == "":
            continue
        entries.append((indent, stripped, lineno))
    # Rebuild entries without lineno for the builder (kept same shape).
    flat = [(e[0], e[1]) for e in entries]

    if not flat:
        return {}

    root_indent = flat[0][0]
    if root_indent != 0:
        raise YAMLParseError("root must not be indented (line 0)")
    return _build(flat, _Index(0), 0)


# --------------------------------------------------------------------------
# Serialization (dump) back into the restricted subset.
# --------------------------------------------------------------------------

def _scalar_repr(value):
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    # Plain if it does not need quoting. Conservative: quote on anything risky.
    risky = not text or text in ("null", "true", "false") or text.strip() != text
    if any(ch in text for ch in ":#{}[],&*!'\"") or " #" in text:
        risky = True
    if risky:
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def dump(data):
    """Serialize back into restricted YAML (2-space indent)."""
    lines = _dump_block(data, 0)
    return "\n".join(lines) + "\n"


def _dump_block(node, indent):
    pad = " " * indent
    if isinstance(node, dict):
        if not node:
            # Empty map: outside the strict subset but preserved defensively.
            return [pad + "{}"]
        out = []
        for key, value in node.items():
            if isinstance(value, (dict, list)):
                if isinstance(value, list) and value == []:
                    out.append(pad + str(key) + ": []")
                elif isinstance(value, dict) and value == {}:
                    out.append(pad + str(key) + ": null")
                else:
                    out.append(pad + str(key) + ":")
                    out.extend(_dump_block(value, indent + 2))
            else:
                out.append(pad + str(key) + ": " + _scalar_repr(value))
        return out
    if isinstance(node, list):
        if not node:
            return [pad + "[]"]
        out = []
        for item in node:
            if isinstance(item, (dict, list)):
                if isinstance(item, dict) and item == {}:
                    out.append(pad + "- null")
                elif isinstance(item, list) and item == []:
                    out.append(pad + "- []")
                else:
                    out.append(pad + "-")
                    out.extend(_dump_block(item, indent + 2))
            else:
                out.append(pad + "- " + _scalar_repr(item))
        return out
    return [pad + _scalar_repr(node)]