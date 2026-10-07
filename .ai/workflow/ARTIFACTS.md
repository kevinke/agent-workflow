# Artifact Contracts

All artifacts live under `.ai/work/<ticket-id>/`. Each has one writer role, an allowed content set, and a forbidden content set.

| Artifact | Writer | Content | Forbidden |
|---|---|---|---|
| evidence.md | scout | Scout Report: Metadata, Decision Questions, Findings, Unknowns, Handoff; FACT / INFERENCE / UNKNOWN entries; important FACTs carry anchors | design proposals, the evidence verdict |
| evidence-audit.md | evidence-auditor | sufficiency answers only | recommendations, designs |
| decision.md | technical-decision (senior-only) | chosen approach, rejected alternatives, invariants, compatibility, API/schema decisions, risks, escalation boundaries | undecided design questions |
| progress.md | ticket-executor | task-granularity log: completed task, files changed, tests run, deviation, open issues | every shell command |
| handoff.md | checkpoint-handoff (or the departing agent) | fixed sections + Repository State block | unverified claims |

## evidence.md (Scout Report, format_version=1)

The Evidence artifact is the Scout Report. It is the only artifact a scout
writes. Design proposals and the evidence verdict (sufficient / insufficient)
are forbidden — the verdict belongs to the evidence-auditor via `set-gate`.

Adopted repos carry a Migration Notice (see MIGRATION.md). Collection rounds
are retained: prior rounds, DQ/F IDs and collection history stay addressable.

### Metadata

Metadata lives in the first fenced yaml block under an exact H2 Metadata
heading; only that block goes through the restricted parser. All other content
is Markdown — never send commands, generic types, or arbitrary prose through
that parser.

Required Metadata fields:

- `artifact_type: evidence`
- `format_version: 1`
- `ticket_id`
- `round` — the positive current collection round; must match Audit/CLI round
- `observed_commit` — repository HEAD at collection time
- `dirty_changes` — string list of relevant working-tree paths, or `[]`
- `created_at`
- `scout_harness`, `scout_model` — Scout provenance

`task_type` and `report_status` are optional descriptive fields, not State
enums. Capture `observed_commit` and `dirty_changes` at collection time and
keep the observed snapshot interpretable.

### Required sections

Required H2 sections, in order: Metadata, Decision Questions, Findings,
Unknowns, Handoff. Optional H2 sections (task-specific, conditional — no fixed
quota): Reproduction, Execution Path, Failure Boundary, Contracts, Constraints,
Change Surface. Bug investigations record reproduction and failure-boundary
outcomes, with reasons when they could not be established.

### Decision Questions

Three to eight questions is guidance, not a quota. If the ticket supplies no
questions, the scout drafts them from the request and may add factual
follow-ups. Ambiguity requiring an architectural choice is escalated, not
answered. Each question uses H3 `DQ-01` (two or more digits) with named fields:

- **Question:** the question as investigated
- **Decision affected:** which decision this question feeds
- **Evidence targets:** likely files, areas, or behaviors worth collecting
- **Answer:** `ANSWERED` | `UNKNOWN`
- **Facts:** linked F-IDs, or an explicit UNKNOWN fact-link value when unresolved

### Findings

Each finding uses H3 `F-01 [FACT | INFERENCE | UNKNOWN]` with named fields:

- **Statement:** one precise claim
- **Questions:** associated DQ IDs
- **Sources:** anchored source list (see below)
- **Method:** `static` | `execution` | `test` | `inference` | `unknown`
- **Scope:** limits of the claim
- **Basis:** required for INFERENCE (cited F-IDs); optional otherwise

Named fields use `**Label:** value`; multiline lists continue below the label.
Recognise fields outside code fences only. FACT means an observed claim, not a
confidence score; optional confidence grades cannot replace evidence. Static
reading, execution, and test verification are distinct methods — do not present
static reading as runtime verification.

Sources accept:

- code anchors: `code: src/example.py:10-14 :: Example.method` — repository-relative file, line or range, symbol when one exists
- data/config anchors: file/line plus a named key or record
- runtime anchors: command, relevant input/fixture, observed result, exit status
- a file without a named symbol uses a justified `:: file scope (no named symbol)` anchor rather than a fabricated function name
- negative searches additionally state search scope and exclusions

### Unknowns

The Unknowns section names the unresolved DQ/F IDs, the decision impact of each,
and the next collection step; explicit `None` is valid. A critical UNKNOWN does
not block report readiness, but it cannot open the Evidence Gate — only the
auditor judges sufficiency.

### Handoff

The Handoff section lists established Fact IDs, decisions still required,
precise missing evidence, areas already investigated, and the stopping reason.
Report readiness and evidence sufficiency are distinct: a report with a
critical UNKNOWN can be ready for audit while the Gate remains insufficient.

## evidence-audit.md

Metadata lives in the first fenced yaml block under an exact H2 Metadata
heading, with required fields: `artifact_type: evidence-audit`,
`format_version: 1`, `ticket_id`, `round`, `gate`, `evidence_sha256`. The
`evidence_sha256` field is the SHA-256 of the audited Evidence report; it is
computed when the gate is recorded and IS written into the audit artifact's
Metadata. The audit artifact's own SHA-256 is never computed and inserted
into itself.

After Metadata, keep exactly the existing four sufficiency-question H2s; each
has a substantive answer or a justified not-applicable:

1. Is the evidence sufficient to enter technical_decision?
2. What is missing?
3. Why might the gap change a decision?
4. What should the next scout collect precisely?

Assess DQ coverage, traceability, verification limits, and decision-changing
unknowns within those questions. Answers only sufficiency — no recommendations,
no designs.

## decision.md

Written only by a senior model (technical-decision role). Contains:

- Chosen approach
- Rejected alternatives
- Invariants
- Compatibility
- API / schema decisions
- Risks
- Escalation boundaries

Adopted repos add a Provenance section recording only the still-valid API/schema/invariants/architecture (see MIGRATION.md).

## progress.md

Execution log at task granularity: completed task, files changed, tests run, deviation from plan, open issues. Not every shell command.

## handoff.md

Fixed sections: What was done / What remains / Important discoveries / Current failure if any / Do not repeat / Next recommended action. Plus a Repository State block: branch, HEAD, uncommitted files, test status.

## v2 structural validation (workflow_version 2)

The grammar above is enforced structurally for Version 2 Tickets; Version 1
Tickets keep their existing semantics. Structural validation checks shapes, not
truth: it never proves a claim or judges a design.

Reading rules:

- Only H2/H3 headings **outside code fences** become sections/records; a fenced
  fake heading is never a boundary.
- Metadata is the **first** fenced yaml block under the exact H2 `Metadata`;
  only that block goes through the restricted parser. Duplicate Metadata keys
  and duplicate DQ/F IDs are errors, as are constructs outside the restricted
  YAML subset (ADR-0002).

Reported structural problems include:

- missing required Metadata fields or required H2 sections, sections out of order
- illegal IDs (DQ-NN / F-NN), missing or illegal finding tag, illegal
  `Method`/`Answer` values
- empty values or bare `<placeholder>` stand-ins in required fields
- dangling references: `Facts`/`Basis` naming an unknown F-ID, `Questions`
  naming an unknown DQ-ID (an explicit `UNKNOWN` fact-link stays valid)
- an `INFERENCE` finding without a `Basis`
- a `code:` source with neither a line reference nor a named symbol/key
- a Metadata `ticket_id` that does not match the Ticket

The Audit keeps exactly the four sufficiency-question H2s; its Metadata
`round`/`gate` must match the State and CLI values, and `evidence_sha256` must
be a SHA-256 digest.

Pending scaffold reports are only WARNed in `requirement`/`evidence_collection`
and are never treated as completed reports; from `evidence_audit` onward the
present reports must be structurally valid. Structural validity is not proof
that acceptance criteria passed.

### Gate binding (workflow_version 2)

Recording the verdict with `set-gate` binds it to the audited bytes: State gains
`evidence.report_sha256` (SHA-256 of `evidence.md`) and `evidence.audit_sha256`
(SHA-256 of `evidence-audit.md`), and the Audit's Metadata `evidence_sha256` must
equal the current Evidence hash. The recorded `round` must name the Evidence
Metadata round. Changing either artifact after a sufficient verdict makes the
binding stale; `validate` and decisionward advances report the same blocker until
the auditor re-audits and re-runs `set-gate`. Version 1 Tickets keep the loose,
unbound gate.

