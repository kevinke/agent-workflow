# Artifact Contracts

All artifacts live under `.ai/work/<ticket-id>/`. Each has one writer role, an allowed content set, and a forbidden content set.

| Artifact | Writer | Content | Forbidden |
|---|---|---|---|
| evidence.md | scout | Scout Report: Metadata, Decision Questions, Findings, Unknowns, Handoff; FACT / INFERENCE / UNKNOWN entries; important FACTs carry anchors | design proposals, the evidence verdict |
| evidence-audit.md | evidence-auditor | sufficiency answers only | recommendations, designs |
| decision.md | technical-decision (senior-only) | chosen approach, rejected alternatives, invariants, compatibility, API/schema decisions, risks, escalation boundaries | undecided design questions |
| plan.md | executor-plan (senior-only) | ordered bounded tasks, each with objective, Fact/decision inputs, allowed and protected scope, invariants, acceptance criteria, verification, dependencies, escalation conditions | an executor-selected or redesigned task |
| review.md | reviewer (senior default, independent context) | reviewed commit, registered Plan identity, acceptance results, verification commands/results, findings, verdict, required rework | a verdict for another commit or an unregistered Plan |
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
- `round` — the positive current collection round (an integer; boolean,
  string, zero, and negative values are rejected); must match Audit/CLI round
- `observed_commit` — the repository HEAD at collection time as a literal
  hexadecimal object ID: a seven-hex-digit abbreviation up to the full object
  ID (never `HEAD`, a branch name, or a `<placeholder>`)
- `dirty_changes` — string list of relevant working-tree paths, or `[]`
- `created_at` — an ISO-8601 timestamp (a bare date or a full timestamp)
- `scout_harness`, `scout_model` — concrete Scout provenance, not placeholders

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
- **Questions:** associated DQ IDs — every finding cites at least one
  established question
- **Sources:** anchored source list (see below)
- **Method:** `static` | `execution` | `test` | `inference` | `unknown`
- **Scope:** limits of the claim
- **Basis:** required for INFERENCE and must cite at least one established
  F-ID; optional otherwise

Named fields use `**Label:** value`; multiline lists continue below the label.
Recognise fields outside code fences only. FACT means an observed claim, not a
confidence score; optional confidence grades cannot replace evidence. Static
reading, execution, and test verification are distinct methods — do not present
static reading as runtime verification.

Sources use a supported family prefix — `code:`, `config:`, `data:`,
`runtime:`, `negative search:`, `inference basis:`, `unknown:` — and any other
entry is rejected as non-concrete:

- code/config/data anchors: `code: src/example.py:10-14 :: Example.method` — a
  repository-relative path, a `:12` line or `:12-18` range (line numbers start
  at 1; a range may not be zero or reversed), and a `::` anchor naming the
  symbol, key, or record. A file without a named symbol uses a justified
  `:: file scope (reason: ...)` anchor rather than a fabricated function name.
- runtime anchors: `runtime: <command> / input: <input or fixture> /
  result: <observed result> / exit: <integer exit status>` — command, input,
  observed result, and integer exit status are required; the labels
  `observed result:` and `exit status:` are accepted aliases of `result:` and
  `exit:`.
- negative searches: `negative search: scope <where searched> /
  exclusions: <excluded areas or none> / result: <outcome>` — scope,
  exclusions, and result are required; a search never needs a fabricated file.
- inference basis: `inference basis: F-01, F-02` — at least one cited F-ID.
- unknown: `unknown: <unobserved item> / collect at: <collection target>` —
  the unobserved item and the collection target are required; allowed only on
  an `F-NN [UNKNOWN]` finding.

These source checks are shapes only: no file existence is verified and no
claim is judged — sufficiency and truth remain the auditor's role.

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

## plan.md (format_version=1)

The Plan is the referenced execution contract, written by the senior
`executor-plan` role and integrated by reference (`source_artifacts.plan`) — never
copied into `.ai/`. It decomposes the decision into ordered, bounded tasks.

Metadata lives in the first fenced yaml block under an exact H2 Metadata
heading, with required fields: `artifact_type: plan`, `format_version: 1`,
`ticket_id`, `task_count` (the number of ordered `Task N` sections).

After Metadata, use ordered H2 `Task 1`, `Task 2`, … Each task carries named H3
sections, in order:

- **Objective** — one bounded step an executor can complete without inventing design
- **Inputs** — referenced Fact IDs and the decision from `decision.md`
- **Allowed changes** — the files or areas the executor may modify
- **Protected scope** — behavior, interfaces, or data that must not change
- **Invariants** — properties that must still hold
- **Acceptance criteria** — observable conditions that make the task complete
- **Verification** — exact commands and expected outcomes
- **Dependencies** — earlier task numbers, or a justified `N/A`
- **Escalation conditions** — what forces a senior decision instead of improvisation

Dependency numbers must reference earlier tasks only; a forward or self
dependency is invalid. A justified `N/A` (or `none`) is valid; a bare empty
placeholder is not. Open architecture decisions prevent handing a task to an
executor.

On a `workflow_version: 2` Ticket, `register-plan <ticket-id> --path <plan>
--total N` reads and validates the Plan, bounds its path to the repository,
checks the declared count, and records `source_artifacts.plan.path` and
`source_artifacts.plan.sha256` (the raw-byte hash) plus the ordered
`implementation.task_hashes`. Registration is allowed only in `planning`, a
recorded senior escalation resolution, or a strictly-appending
`changes_requested` review; a rejected registration changes no State bytes.

## review.md (format_version=1)

The Review is the Reviewer's structural verdict on the current change and
registered Plan. The Reviewer owns technical conformance in an independent
context (senior default); mechanical checkpoint-handoff alone cannot supply it.

### Metadata

Metadata lives in the first fenced yaml block under an exact H2 Metadata
heading, with required fields: `artifact_type: review`, `format_version: 1`,
`ticket_id`, `reviewed_commit`, `plan_sha256`, and `verdict`
(`pass` | `changes_requested`).

`reviewed_commit` must be a literal hexadecimal Git object ID: the
repository's full object ID, or an unambiguous abbreviation of at least seven
hex digits, resolving to a commit that is an ancestor of the current HEAD.
HEAD, branch and tag names are rejected even when they resolve — a recorded
review must never follow a moving ref — and a ref named like a hexadecimal
prefix never takes precedence over the object carrying it.

### Required sections

Required H2 sections, in order, after Metadata: `Acceptance results`,
`Verification results`, `Findings`, `Required rework`. `Acceptance results` and
`Verification results` must be substantive for BOTH verdicts; `Findings` and
`Required rework` may be the explicit text `None` for a `pass` and must be
substantive for a `changes_requested`. Extra nonreserved prose sections are
allowed.

Recording the verdict with `set-review <ticket-id> --verdict pass|changes_requested`
binds it to the Review artifact's raw-byte SHA-256, the full resolved commit ID
(stored once in State, for both verdicts), and the registered Plan SHA-256 (see
`STATE_SCHEMA.md`). A missing or placeholder artifact, a Metadata `verdict` that
disagrees with the CLI, a `plan_sha256` that disagrees with the registered Plan,
a `reviewed_commit` that is symbolic, ambiguous, a non-commit, or an unrelated
history, or any change to the reviewed code, tests, fixtures, or Plan since the
reviewed commit rejects the command and leaves State unchanged. Only this
Ticket's own `state.yaml`, `progress.md`, `handoff.md`, and `review.md` are
exempt from the code-drift check. Structural validity is not proof that
acceptance criteria passed.

Both recorded verdicts are re-assessed against their immutable bindings by
`validate`, `resume`, and the mutation guards: a `pass` and a
`changes_requested` each keep matching Review bytes, the same literal commit,
the registered Plan, and unchanged reviewed code. A previously stored symbolic
binding (for example `reviewed_commit: HEAD` or a branch name from an older
State) is stale: it is reported and requires a new independent review — today's
HEAD is never resolved as the old approval. A `pass` completes the ticket only
while it is current: `review -> done` is rejected once the Review artifact, the
registered Plan, or the reviewed code changes. A `changes_requested` is repaired
append-only — the senior registers an appending rework Plan (`register-plan`)
and `review -> implementation` clears the failed verdict to `pending`,
preserving the completed prefix and routing to the first appended task. The
recorded Review must be unchanged for that repair; a stale failed Review is
re-recorded, not reused. The re-registration itself may replace the failed
Review's Plan identity, and only that Plan drift is excused — never source-code
drift or changed Review bytes — and only while the completed task contracts are
unchanged. A recorded `pass` never inherits that exception.

## progress.md

Execution log at task granularity: completed task, files changed, tests run, deviation from plan, open issues. Not every shell command.

## handoff.md

Fixed sections, in order: What was done / What remains / Important discoveries / Artifact identity / Verification limits / Known relevant drift / Current failure (if any; the shorter heading `Current failure` is accepted as its alias) / Do not repeat / Next recommended action. Plus a Repository State block with the four fields Branch, HEAD, Uncommitted files, and Test status.

### Handoff readiness (workflow_version 2)

`contracts.validate_handoff` checks the readiness syntax of a handoff — shapes only, never narrative truth:

- every required section present, and prose sections substantive (not empty, not one whole-value template token; multiline template blocks are detected too);
- `Artifact identity` and `Known relevant drift` keep structured bullets, and every bullet's label value is concrete — the Evidence/Audit/Decision/Plan/Review identities and the drift bullets may not carry whole-value template tokens or standalone `<placeholder>` words;
- `Repository State` carries concrete Branch/HEAD/Uncommitted files/Test status values.

Comparisons and code literals that merely contain angle brackets (generics, inline code, `a < b`) are not placeholders. Explicit `None` and a justified `N/A — reason` are legitimate where no item exists.

Readiness is a **transfer boundary, not proof of acceptance**. Early drafts stay permitted: outside the boundaries the same problems are WARN notices. The gates are entering `review` (implementation -> review), completing to `done`, continuing in `review`/`done` (validate and resume through the shared phase checks), and clearing an implementation/review recovery — a rejected gate leaves State unchanged. A ready handoff never verifies that the narrative is true and never implies the acceptance criteria passed.

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
- a Metadata `round` that is not a positive integer (boolean, string, zero, and
  negative rounds rejected; the Evidence, Audit, and CLI rounds must agree), an
  `observed_commit` that is not a literal 7–64 hex-digit object ID, a
  non-ISO-8601 `created_at`, a non-string-list `dirty_changes`, or placeholder
  `scout_harness`/`scout_model`
- dangling references: `Facts`/`Basis` naming an unknown F-ID, `Questions`
  naming an unknown DQ-ID (an explicit `UNKNOWN` fact-link stays valid)
- an ANSWERED question citing no existing F-ID, a finding citing no existing
  DQ-ID, or an INFERENCE whose `Basis` cites no existing F-ID
- a Sources entry that is not a supported concrete family (a line-only or
  symbol-only code anchor, an unlabeled `trust me` entry, a runtime source
  without command/input/result/integer exit, a negative search without
  scope/exclusions/result, an `inference basis` without F-IDs, or an
  `unknown:` source off an [UNKNOWN] finding or without an unobserved item and
  collection target)
- a Metadata `ticket_id` that does not match the Ticket

The Audit keeps exactly the four sufficiency-question H2s; its Metadata
`round` (a positive integer) and `gate` must match the State and CLI values,
and `evidence_sha256` must be a SHA-256 digest.

The Plan (see above) is validated as ordered `Task N` sections with the nine
required H3 fields; contiguous task numbers, no forward/self dependency, and a
`task_count` agreeing with the sections are required. Its per-task identity is
the **canonical task hash**: SHA-256 of the task's section with CRLF changed to
LF and trailing whitespace removed, so line-ending conversion alone does not
rewrite registered history.

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

## Raw-byte transport (Git attributes)

Every SHA-256 binding above hashes the artifact's **raw bytes** — line endings
included; bytes are never normalized before hashing. Git text normalization
(`core.autocrlf`, the `text` attribute) can rewrite those bytes on a fresh
clone or checkout and invalidate every binding, so transport is protected and
made visible:

- `ai-workflow init` installs a single-purpose `.ai/work/.gitattributes`
  containing exactly `** -text` — but only when absent. An existing attribute
  file is never overwritten, and repeated init is byte-stable. The rule
  disables end-of-line conversion for everything under `.ai/work/`, so bound
  artifact bytes survive checkouts regardless of `autocrlf`.
- **Manual external-Plan rule:** a Plan outside `.ai/work/` is not covered by
  that file. Pin it with an explicit per-path `-text` rule in a root
  `.gitattributes` (e.g. `docs/plan.md -text`). Git attributes patterns split
  on whitespace, so a path containing a space cannot be written literally —
  use a glob instead (e.g. `docs/*.md -text`).
- `validate` and `resume` report a WARN-level transport notice for every bound
  artifact (sufficient-gate Evidence/audit bytes, a recorded Review artifact)
  and the registered Plan whose effective `text` attribute is anything other
  than unset — `text=auto`, `set`, or unspecified (autocrlf decides). The
  notice is visible only and never becomes a new execution gate; adding the
  `-text` rule is always the user's explicit decision. The assessment is
  read-only: it never edits root attributes or global config, and never
  renormalizes tracked files.

Adopting protection for existing Tickets keeps their bindings: adding the
attributes file changes no committed artifact content, so current SHA-256
bindings stay current. Commit the attributes file itself and do **not**
renormalize (`git add --renormalize .` rewrites bytes and invalidates
bindings). Where Git attributes are unavailable — artifacts leaving the
repository by mail or attachment — a ZIP archive is the transport escape
hatch: an archive carries the bytes verbatim without attribute support.


## Verified export: `archive-artifacts` (manifest.json, format_version 1)

`ai-workflow archive-artifacts <ticket-id> --output <new.zip>` publishes a
Ticket's work artifacts as a single ZIP of **exact raw bytes** plus a
`manifest.json` describing them. It is a verification boundary, not a generic
backup API: a v1 Ticket, a pending Review, or any stale binding is refused
(exit 1); both a `pass` and a *current* `changes_requested` verdict export.

- **Export scope.** The archive collects the exact raw bytes of the State
  (`state.yaml`), Evidence, Evidence Audit, Decision, Progress, Handoff and
  Review artifacts, plus the registered Plan **at its actual registered source
  path** (from `source_artifacts.plan.path`), under safe unique
  repository-relative paths. Membership is fixed by this contract; the command
  takes no per-file options.
- **Currentness.** Before publication the collected bytes themselves are
  compared with every recorded hash — `evidence.report_sha256`,
  `evidence.audit_sha256`, `review.artifact_sha256`,
  `review.plan_sha256`/`source_artifacts.plan.sha256` — and the Review
  bindings are assessed WITHOUT the repair path's rework exception: a stale
  failed Review or an appended rework Plan awaiting a new review cannot be
  exported. Hashes are over raw bytes; line endings are never normalized.
- **Manifest.** `manifest.json` (JSON, `format_version: 1`) carries
  `ticket_id`, `snapshot_head` (the Git commit the export was taken at) and
  `entries`: a list sorted by repository-relative path, each entry holding
  `path`, `sha256` (of the member's raw bytes) and `bound_sha256` — the
  recorded State hash for the four bound members (Evidence, Audit, Review,
  registered Plan), and `null` for supporting files (`state.yaml`,
  `decision.md`, `progress.md`, `handoff.md`), which were never previously
  bound and are not pretended to be.
- **Safe publication.** Member names are validated before any write
  (normalized relative paths, no traversal, no duplicates; `manifest.json` is
  reserved), collected inputs must symlink-resolve inside the repository, and
  the output must not collide with a collected input or an existing file. The
  ZIP is built beside the output and published with a non-overwriting atomic
  hard link — `os.replace` is never used, so a pre-existing output keeps its
  exact bytes and a failed write leaves no partial archive. All failures are
  reported as errors; nothing is written on refusal.
- **Resuming elsewhere.** The archive re-verifies byte identity on arrival,
  but byte hashes alone do not re-establish the reviewed code: resume an
  exported Ticket WITH the matching code repository/history (the manifest's
  `snapshot_head` and `review.reviewed_commit` name the commits), or treat
  the archive as durable evidence only.
