"""Bounded artifact reader and structural validators (SCOUT-002).

Implements the frozen artifact grammar in `.ai/workflow/ARTIFACTS.md`:

- Markdown headings are recognised only outside code fences; a fenced fake
  H3 never becomes a record boundary.
- Metadata is the first fenced yaml block under the exact H2 `Metadata`;
  only that block goes through the restricted parser (ADR-0002). Duplicate
  metadata keys are rejected before the parser could silently overwrite
  them, and restricted-YAML violations surface as ContractError.
- Named fields use `**Label:** value`; multiline lists continue below the
  label. Records are normalised to {id, kind, fields, tag?} dicts and H2
  bodies to plain strings.

Structural validation reports problems as a list of strings; it judges
shapes (IDs, labels, anchors, placeholders), never claim truth or designs.
"""

import hashlib
import os
import re

import parser

__all__ = ["ContractError", "read_artifact", "read_plan", "sha256_file",
           "validate_evidence", "validate_audit"]


class ContractError(Exception):
    """Raised when an artifact violates the bounded grammar."""


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def sha256_file(path):
    """SHA-256 of the file's raw bytes, line endings included."""
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


# ---------------------------------------------------------------------------
# Bounded Markdown scan
# ---------------------------------------------------------------------------

_H2_RE = re.compile(r"^## (?!#)(.+?)\s*$")
_H3_RE = re.compile(r"^### (?!#)(.+?)\s*$")
_FIELD_RE = re.compile(r"^\*\*([^*]+?):\*\*\s*(.*)$")
_FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
_META_KEY_RE = re.compile(r"^(.*?):[ \t]*(.*)$")

DQ_ID_RE = re.compile(r"^DQ-\d{2,}$")
F_ID_RE = re.compile(r"^F-\d{2,}$")
F_REF_RE = re.compile(r"\bF-\d{2,}\b")
DQ_REF_RE = re.compile(r"\bDQ-\d{2,}\b")
_CODE_LINE_RE = re.compile(r":\d+(?:-\d+)?(?=\s|$)")
_PLACEHOLDER_RE = re.compile(r"^<[^<>\n]*>$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

FINDING_TAGS = {"FACT", "INFERENCE", "UNKNOWN"}
METHODS = {"static", "execution", "test", "inference", "unknown"}
ANSWERS = {"ANSWERED", "UNKNOWN"}


def _scan(text):
    """Split Markdown into H2 sections and H3 records, ignoring fences.

    Returns (sections, records, fenced) where sections maps H2 heading text
    to the body string (fenced content excluded, subheadings included),
    records is a list of {section, id, kind, tag, fields} dicts for H3s
    inside record-bearing sections, and fenced maps H2 heading text to the
    list of fenced code blocks (each a list of lines) in that section.
    Duplicate H2 headings or duplicate H3 IDs raise ContractError.
    """
    sections = {}
    records = []
    fenced = {}
    seen_ids = set()
    fence = None  # active fence marker (``` or ~~~) or None
    fence_block = None  # lines of the open fence block, collected at H2 level
    current = None  # (level, heading text, body lines list)
    current_record = None
    section_name = None

    def close_current():
        nonlocal current, current_record
        if current is None:
            return
        level, heading, body = current
        if level == 2:
            sections[heading] = "\n".join(body).strip("\n")
        else:
            record = current_record
            record["section"] = section_name
            record["fields"] = _fields(body)
            records.append(record)
        current = None
        current_record = None

    for line in text.splitlines():
        m = _FENCE_RE.match(line)
        if m:
            marker = m.group(1)
            if fence is None:
                fence = marker[0] * 3  # opening fence
                fence_block = []
                continue
            if marker.startswith(fence):  # closing fence of same char family
                if current is not None and current[0] == 2:
                    fenced.setdefault(current[1], []).append(fence_block)
                fence = None
                fence_block = None
            continue
        if fence is not None:
            if fence_block is not None:
                fence_block.append(line)
            continue
        h2 = _H2_RE.match(line)
        if h2:
            close_current()
            heading = h2.group(1).strip()
            if heading in sections:
                raise ContractError("duplicate H2 heading %r" % heading)
            sections[heading] = ""
            section_name = heading
            current = (2, heading, [])
            continue
        h3 = _H3_RE.match(line)
        if h3 and current is not None:
            close_current()
            heading = h3.group(1).strip()
            rec_id = heading.split()[0]
            tag = None
            tm = re.search(r"\[(FACT|INFERENCE|UNKNOWN)\]\s*$", heading)
            if tm:
                tag = tm.group(1)
            if rec_id in seen_ids:
                raise ContractError("duplicate record id %r" % rec_id)
            seen_ids.add(rec_id)
            current = (3, heading, [])
            current_record = {"id": rec_id, "kind": None, "tag": tag}
            continue
        if current is not None:
            current[2].append(line)
    close_current()
    return sections, records, fenced


def _fields(body_lines):
    """Parse `**Label:** value` fields; multiline lists continue the label."""
    fields = {}
    label = None
    fence = None
    for line in body_lines:
        m = _FENCE_RE.match(line)
        if m:
            marker = m.group(1)
            if fence is None:
                fence = marker[0] * 3
            elif marker.startswith(fence):
                fence = None
            continue
        if fence is not None:
            continue
        fm = _FIELD_RE.match(line)
        if fm:
            label = fm.group(1).strip()
            fields[label] = fm.group(2).strip()
            continue
        if label is not None and line.strip():
            fields[label] = (fields[label] + "\n" + line.strip()).strip("\n")
        elif not line.strip():
            label = None
    return fields


def _parse_metadata(sections, fenced):
    """Parse the first fenced yaml block of the Metadata H2 section."""
    if "Metadata" not in sections:
        raise ContractError("missing required H2 section 'Metadata'")
    blocks = fenced.get("Metadata") or []
    if not blocks:
        raise ContractError("Metadata section has no fenced yaml block")
    return _metadata_from_lines(blocks[0])


def _metadata_from_lines(block):
    seen = set()
    for raw in block:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.startswith((" ", "\t")):
            continue  # nested list/member line, not a top-level key
        m = _META_KEY_RE.match(raw)
        if not m:
            raise ContractError("malformed Metadata YAML line %r" % raw)
        key = m.group(1).strip().strip('"').strip("'")
        if key in seen:
            raise ContractError("duplicate Metadata key %r" % key)
        seen.add(key)
    try:
        data = parser.parse("\n".join(block) + "\n")
    except parser.YAMLParseError as exc:
        raise ContractError("malformed Metadata YAML: %s" % exc)
    if not isinstance(data, dict):
        raise ContractError("Metadata YAML must be a map")
    return data


def read_artifact(path, kind):
    """Read a bounded Markdown artifact into {metadata, sections, records}.

    `kind` is "evidence" or "evidence-audit". Evidence records carry
    kind=question (Decision Questions) or kind=finding (Findings) with an
    optional tag for findings; the audit has H2 sections only.
    """
    try:
        with open(path, "rb") as fh:
            text = fh.read().decode("utf-8")
    except OSError as exc:
        raise ContractError("cannot read %s: %s" % (path, exc))
    except UnicodeDecodeError as exc:
        raise ContractError("artifact is not UTF-8: %s" % exc)

    sections, records, fenced = _scan(text)
    metadata = _parse_metadata(sections, fenced)
    if kind == "evidence":
        for rec in records:
            if rec["section"] == "Decision Questions":
                rec["kind"] = "question"
            elif rec["section"] == "Findings":
                rec["kind"] = "finding"
            else:
                rec["kind"] = "record"
    elif kind == "evidence-audit":
        records = []
    else:
        raise ContractError("unknown artifact kind %r" % kind)
    return {"metadata": metadata, "sections": sections, "records": records}


# ---------------------------------------------------------------------------
# Plan reader (registered execution contracts)
# ---------------------------------------------------------------------------

PLAN_TASK_FIELDS = [
    "Objective", "Inputs", "Allowed changes", "Protected scope",
    "Invariants", "Acceptance criteria", "Verification", "Dependencies",
    "Escalation conditions",
]

_TASK_HEADING_RE = re.compile(r"^Task (\d+)$")


def _scan_plan(text):
    """Ordered H2 sections for a Plan, with nested H3 bodies and fences.

    Like `_scan`, a heading inside a code fence is never a boundary. Unlike
    `_scan`, the raw body of an H2 section keeps its nested H3 subheadings (so a
    `Task N` section can be hashed and split into named fields), and repeated H3
    labels across tasks are not treated as duplicate records. Returns
    (order, bodies, fenced): the section headings in order, heading -> raw body
    text (heading line included), and heading -> list of fenced blocks.
    """
    order = []
    bodies = {}
    fenced = {}
    current = None
    fence = None
    fence_block = None
    for line in text.splitlines():
        m = _FENCE_RE.match(line)
        if fence is not None:
            if m and m.group(1).startswith(fence):
                if current is not None and fence_block is not None:
                    fenced.setdefault(current, []).append(fence_block)
                fence = None
                fence_block = None
            elif fence_block is not None:
                fence_block.append(line)
            if current is not None:
                bodies[current].append(line)
            continue
        if m:
            fence = m.group(1)[0] * 3
            fence_block = []
            if current is not None:
                bodies[current].append(line)
            continue
        h2 = _H2_RE.match(line)
        if h2:
            heading = h2.group(1).strip()
            if heading in bodies:
                raise ContractError("duplicate H2 heading %r" % heading)
            bodies[heading] = [line]
            order.append(heading)
            current = heading
            continue
        if current is not None:
            bodies[current].append(line)
    return order, {h: "\n".join(lines) for h, lines in bodies.items()}, fenced


def _plan_task_fields(body):
    """Parse a `Task N` section body into H3 `heading -> body text` fields.

    Fenced content is ignored (a heading inside a fence is not a boundary);
    duplicate H3 headings within one task raise ContractError.
    """
    fields = {}
    lines = body.split("\n")
    label = None
    fence = None
    for line in lines[1:]:  # drop the H2 Task heading line
        m = _FENCE_RE.match(line)
        if fence is not None:
            if m and m.group(1).startswith(fence):
                fence = None
            continue
        if m:
            fence = m.group(1)[0] * 3
            continue
        h3 = _H3_RE.match(line)
        if h3:
            label = h3.group(1).strip()
            if label in fields:
                raise ContractError("plan: duplicate field heading %r" % label)
            fields[label] = ""
            continue
        if label is not None and line.strip():
            fields[label] = (fields[label] + "\n" + line.strip()).strip("\n")
    return fields


def _justified_na(value):
    text = (value or "").strip().lower()
    return text.startswith("n/a") or text.startswith("not applicable") \
        or text == "none"


def _canonical_task_hash(section):
    """SHA-256 of a task section: CRLF -> LF, trailing whitespace removed."""
    normalised = section.replace("\r\n", "\n")
    lines = [line.rstrip() for line in normalised.split("\n")]
    return hashlib.sha256("\n".join(lines).rstrip().encode("utf-8")).hexdigest()


def _check_plan_task(fields, number):
    for name in PLAN_TASK_FIELDS:
        if name not in fields:
            raise ContractError(
                "plan task %d: missing field heading %r" % (number, name))
        if _is_placeholder(fields[name]):
            raise ContractError(
                "plan task %d: field %r is empty or a bare placeholder"
                % (number, name))
    deps = fields["Dependencies"]
    if not _justified_na(deps):
        for ref in re.findall(r"\d+", deps):
            if int(ref) >= number:
                raise ContractError(
                    "plan task %d: dependency %s does not reference an earlier "
                    "task" % (number, ref))


def read_plan(path, ticket_id):
    """Read a Plan artifact into an ordered list of task records.

    Each record is {number: int, fields: dict[str, str], sha256: str}; the hash
    is the canonical task-section digest (CRLF normalised, trailing whitespace
    removed). Structural problems (missing file/Metadata/fields, a noncontiguous
    or non-`Task N` heading order, a forward/self dependency, or a Metadata
    `task_count` that disagrees with the sections) raise ContractError.
    """
    try:
        with open(path, "rb") as fh:
            text = fh.read().decode("utf-8")
    except OSError as exc:
        raise ContractError("cannot read %s: %s" % (path, exc))
    except UnicodeDecodeError as exc:
        raise ContractError("plan is not UTF-8: %s" % exc)

    order, bodies, fenced = _scan_plan(text)
    if "Metadata" not in bodies:
        raise ContractError("plan: missing required H2 section 'Metadata'")
    blocks = fenced.get("Metadata") or []
    if not blocks:
        raise ContractError("plan: Metadata section has no fenced yaml block")
    md = _metadata_from_lines(blocks[0])
    if md.get("artifact_type") != "plan":
        raise ContractError(
            "plan: Metadata artifact_type must be 'plan' (got %r)"
            % md.get("artifact_type"))
    if not _is_int(md.get("format_version")) or md.get("format_version") != 1:
        raise ContractError("plan: Metadata format_version must be 1")
    if md.get("ticket_id") != ticket_id:
        raise ContractError(
            "plan: Metadata ticket_id %r does not match %r"
            % (md.get("ticket_id"), ticket_id))
    if not _is_int(md.get("task_count")) or md.get("task_count") <= 0:
        raise ContractError("plan: Metadata task_count must be a positive integer")

    headings = [h for h in order if _TASK_HEADING_RE.match(h)]
    if not headings:
        raise ContractError("plan: no ordered 'Task N' H2 sections found")
    records = []
    for index, heading in enumerate(headings, start=1):
        number = int(_TASK_HEADING_RE.match(heading).group(1))
        if number != index:
            raise ContractError(
                "plan: task sections must be contiguous Task 1..Task N; found "
                "%r at position %d" % (heading, index))
        fields = _plan_task_fields(bodies[heading])
        _check_plan_task(fields, number)
        records.append({"number": number, "fields": fields,
                        "sha256": _canonical_task_hash(bodies[heading])})

    if md["task_count"] != len(records):
        raise ContractError(
            "plan: Metadata task_count %r does not match the %d task sections"
            % (md["task_count"], len(records)))
    return records


# ---------------------------------------------------------------------------
# Structural validation
# ---------------------------------------------------------------------------

def _is_placeholder(value):
    if value is None:
        return True
    text = str(value).strip()
    return not text or bool(_PLACEHOLDER_RE.match(text))


def _field_problems(problems, owner, fields, labels):
    for label in labels:
        if label not in fields:
            problems.append("%s: missing field '%s'" % (owner, label))
        elif _is_placeholder(fields[label]):
            problems.append(
                "%s: field '%s' is empty or a bare placeholder" % (owner, label))


def _metadata_problems(flag, prefix, md, required, checks):
    for key in required:
        if key not in md or md[key] is None or md[key] == "":
            flag("%s: missing required Metadata field '%s'" % (prefix, key))
    for key, check in checks:
        if key in md and md[key] is not None and not check(md[key]):
            flag("%s: illegal Metadata field '%s' value %r" % (prefix, key, md[key]))


def _is_int(value):
    return not isinstance(value, bool) and isinstance(value, int)


def _string_list(value):
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


_EVIDENCE_REQUIRED_METADATA = [
    "artifact_type", "format_version", "ticket_id", "round",
    "observed_commit", "dirty_changes", "created_at",
    "scout_harness", "scout_model",
]
_EVIDENCE_SECTIONS = ["Metadata", "Decision Questions", "Findings",
                      "Unknowns", "Handoff"]
_DQ_FIELDS = ["Question", "Decision affected", "Evidence targets",
              "Answer", "Facts"]
_F_FIELDS = ["Statement", "Questions", "Sources", "Method", "Scope"]


def validate_evidence(report, ticket_id):
    """Structural problems of an Evidence report; [] means well-formed."""
    problems = []
    md = report.get("metadata") or {}

    def flag(msg):
        problems.append(msg)

    _metadata_problems(flag, "evidence", md, _EVIDENCE_REQUIRED_METADATA, [
        ("artifact_type", lambda v: v == "evidence"),
        ("format_version", lambda v: _is_int(v) and v == 1),
        ("round", lambda v: _is_int(v) and v > 0),
        ("dirty_changes", _string_list),
        ("task_type", lambda v: isinstance(v, str)),
        ("report_status", lambda v: isinstance(v, str)),
    ])
    if md.get("ticket_id") and md.get("ticket_id") != ticket_id:
        problems.append("evidence: Metadata ticket_id %r does not match %r"
                        % (md.get("ticket_id"), ticket_id))

    sections = report.get("sections") or {}
    for name in _EVIDENCE_SECTIONS:
        if name not in sections:
            problems.append("evidence: missing required H2 section %r" % name)
    present = [n for n in sections if n in _EVIDENCE_SECTIONS]
    if present != [n for n in _EVIDENCE_SECTIONS if n in sections]:
        problems.append("evidence: required H2 sections out of order "
                        "(expected %s)" % ", ".join(_EVIDENCE_SECTIONS))

    records = report.get("records") or []
    questions = [r for r in records if r.get("kind") == "question"]
    findings = [r for r in records if r.get("kind") == "finding"]
    if not questions:
        problems.append("evidence: no Decision Questions recorded (H3 DQ-01 ...)")
    if not findings:
        problems.append("evidence: no Findings recorded (H3 F-01 [FACT])")

    q_ids, f_ids = set(), set()
    for rec in questions:
        rid = rec.get("id", "?")
        if not DQ_ID_RE.match(rid):
            problems.append("evidence: illegal question id %r (expected DQ-NN)" % rid)
        q_ids.add(rid)
        _field_problems(problems, rid, rec.get("fields") or {}, _DQ_FIELDS)
        answer = (rec.get("fields") or {}).get("Answer")
        if answer and answer not in ANSWERS:
            problems.append("%s: Answer must be ANSWERED or UNKNOWN, got %r"
                            % (rid, answer))
    for rec in findings:
        rid = rec.get("id", "?")
        if not F_ID_RE.match(rid):
            problems.append("evidence: illegal finding id %r (expected F-NN)" % rid)
        f_ids.add(rid)
        if rec.get("tag") not in FINDING_TAGS:
            problems.append("%s: missing or illegal [FACT|INFERENCE|UNKNOWN] tag" % rid)
        fields = rec.get("fields") or {}
        _field_problems(problems, rid, fields, _F_FIELDS)
        method = fields.get("Method")
        if method and method not in METHODS:
            problems.append("%s: Method must be one of %s, got %r"
                            % (rid, ", ".join(sorted(METHODS)), method))
        if rec.get("tag") == "INFERENCE" and _is_placeholder(fields.get("Basis")):
            problems.append("%s: INFERENCE finding requires a Basis (cited F-IDs)" % rid)
        for line in (fields.get("Sources") or "").splitlines():
            item = line.strip()
            if item.startswith("- "):
                item = item[2:].strip()
            if item.startswith("code:"):
                body = item[len("code:"):].strip()
                has_line = bool(_CODE_LINE_RE.search(body))
                has_anchor = "::" in body and body.split("::")[-1].strip()
                if not (has_line or has_anchor):
                    problems.append(
                        "%s: code source is missing a line reference and a "
                        "named symbol or key: %r" % (rid, item))

    for rec in questions:
        fields = rec.get("fields") or {}
        facts = fields.get("Facts") or ""
        for ref in F_REF_RE.findall(facts):
            if ref not in f_ids:
                problems.append("%s: Facts references unknown finding %s"
                                % (rec.get("id", "?"), ref))
    for rec in findings:
        fields = rec.get("fields") or {}
        for ref in DQ_REF_RE.findall(fields.get("Questions") or ""):
            if ref not in q_ids:
                problems.append("%s: Questions references unknown question %s"
                                % (rec.get("id", "?"), ref))
        for ref in F_REF_RE.findall(fields.get("Basis") or ""):
            if ref not in f_ids:
                problems.append("%s: Basis references unknown finding %s"
                                % (rec.get("id", "?"), ref))
    return problems


_AUDIT_SECTIONS = [
    "Is the evidence sufficient to enter technical_decision?",
    "What is missing?",
    "Why might the gap change a decision?",
    "What should the next scout collect precisely?",
]
_AUDIT_REQUIRED_METADATA = [
    "artifact_type", "format_version", "ticket_id", "round", "gate",
    "evidence_sha256",
]


def validate_audit(report, ticket_id, gate, round_no):
    """Structural problems of an Audit; gate/round bind to the CLI values."""
    problems = []
    md = report.get("metadata") or {}

    def flag(msg):
        problems.append(msg)

    _metadata_problems(flag, "evidence-audit", md, _AUDIT_REQUIRED_METADATA, [
        ("artifact_type", lambda v: v == "evidence-audit"),
        ("format_version", lambda v: _is_int(v) and v == 1),
        ("gate", lambda v: v in ("sufficient", "insufficient")),
        ("evidence_sha256", lambda v: isinstance(v, str) and bool(_SHA256_RE.match(v))),
    ])
    if md.get("ticket_id") and md.get("ticket_id") != ticket_id:
        problems.append("evidence-audit: Metadata ticket_id %r does not match %r"
                        % (md.get("ticket_id"), ticket_id))
    if _is_int(md.get("round")) and _is_int(round_no) and md["round"] != round_no:
        problems.append("evidence-audit: Metadata round %r does not match CLI round %r"
                        % (md["round"], round_no))
    if md.get("gate") and md["gate"] != gate:
        problems.append("evidence-audit: Metadata gate %r does not match CLI gate %r"
                        % (md.get("gate"), gate))

    sections = report.get("sections") or {}
    for name in _AUDIT_SECTIONS:
        if name not in sections:
            problems.append("evidence-audit: missing required H2 section %r" % name)
        elif _is_placeholder(sections[name].strip()):
            problems.append(
                "evidence-audit: section %r has no substantive answer" % name)
    extra = [n for n in sections
             if n not in _AUDIT_SECTIONS and n != "Metadata"]
    if extra:
        problems.append("evidence-audit: unexpected extra H2 sections %s "
                        "(exactly the four sufficiency questions allowed)"
                        % ", ".join(repr(n) for n in extra))
    return problems
