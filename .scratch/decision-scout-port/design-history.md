# Decision Scout Port: Record of Origin and Fit Analysis

Status: draft
Type: design-note (pre-spec)

## Origin

This document records the origin and analysis of a proposal to adopt an external
"Decision Scout" design into this repository.

The proposal arrived as a chat reply (external conversation, Chinese; preserved
verbatim in [original-proposal.md](original-proposal.md)) arguing that
pre-planning repository research should be packaged as a **Skill** rather than a
single prompt, because it is a stable **agent work protocol**, not a one-off
questioning technique. The proposed protocol pipeline:

```text
Task / Issue -> Triage -> Decision Questions -> Scout -> Evidence
  -> facts/<task-id>.scout.md -> Planner -> tickets/<task-id>.md
  -> Implementer -> Reviewer
```

Key claims in the proposal:

1. Role isolation: Scout is a fact-finder ("X is a fact, evidence follows"),
   Planner is the decision-maker ("because X, choose Y"), Implementer executes,
   Reviewer verifies independently. Planners should trust Scout **evidence**,
   not Scout **reasoning** — so cheap models can scout while senior models decide.
2. Strict separation of FACT / INFERENCE / UNKNOWN, plus confidence levels
   (HIGH / MEDIUM / LOW / UNKNOWN) on every important finding, because the main
   handoff failure mode is "the next model cannot tell whether the previous
   model's statement was observed or guessed".
3. A locked-down Scout Report format (`facts/<task-id>.scout.md`) as the
   machine-to-machine handoff artifact — argued to be more important than the
   prompt itself, since it is what enables Claude/DS/GLM/GPT interchangeability
   via Markdown artifacts rather than chat context.
4. Methodology content: task classification (BUG_FIX / FEATURE / REFACTOR /
   INTEGRATION / PERFORMANCE / SECURITY / MIGRATION), 3–8 "decision questions"
   that bound the search, evidence priority (repro > tests > logs > code >
   schemas > docs > inference), fact categories (current behavior, execution
   path, failure boundary, contracts, constraints, safeguards, change surface),
   search/cost discipline, stop conditions, and prohibited behavior (no
   implementation, no design proposals, no repo-wide exploration by default).
5. Task-type-specific decision-question patterns (e.g. BUG_FIX asks "where does
   state first become incorrect?"; REFACTOR asks "who references the target
   abstraction?").
6. The next step named by the proposal: define the Planner output protocol
   (`ticket.md`: implementation scope, forbidden-modification scope, acceptance
   criteria, test requirements, risks) to close the Scout -> Planner ->
   Implementer chain.

## Fit analysis against this repository

The analysis (conducted in conversation against the current repo state; full
verbatim record in [fit-analysis.md](fit-analysis.md)) concluded:

**The repository already implements roughly 80% of the proposal, in a stricter
form.** This is convergence, not a new import.

Already present:

- Role isolation and model-tier routing: `.ai/workflow/ROLES.md` — `scout`
  (cheap) owns evidence_collection only; `technical-decision` and
  `executor-plan` are senior; design proposals are forbidden in evidence.md
  (`.ai/workflow/ARTIFACTS.md`).
- FACT / INFERENCE / UNKNOWN with anchors (file, symbol, line, command, test
  result): `.ai/workflow/templates/evidence.md`.
- An evidence **audit gate** (`evidence-auditor`, senior) that judges
  sufficiency and can send the ticket back for followup evidence — stricter
  than the proposal, which has no audit loop.
- A handoff contract with fixed sections including "Do not repeat"
  (`.ai/workflow/ARTIFACTS.md`), covering the proposal's "Non-Relevant
  Findings" idea.
- Repo-as-source-of-truth state machine (`state.yaml`), making the workflow
  model-agnostic across harnesses — the proposal's stated end goal.

**Architecture conflict to respect:** the proposal says "put the methodology in
SKILL.md". This violates ADR-0001 (repo-native protocol over harness skills).
Existing skills such as `.agents/skills/repo-scout/SKILL.md` are deliberately
thin adapters; business rules live in `.ai/workflow/`. Any ported content must
land in the protocol layer, with at most a pointer added to the skill.

### Incremental value in the proposal (what the repo lacks)

| Proposal content | Repo gap | Value |
|---|---|---|
| Task classification (task_type) | `state.yaml` has no task-type field | Worth adding; drives the question patterns below |
| Decision Questions (3–8 structured, decision-tied questions bounding scout search) | Scout collects evidence with no structured question layer | Highest-value increment — directly bounds cheap-model search |
| Confidence levels (HIGH/MEDIUM/LOW/UNKNOWN) | Only FACT/INFERENCE/UNKNOWN | Partially redundant (FACT already implies verified); optional |
| Rich report sections (reproduction, execution path, failure boundary, contracts, constraints, change surface, planner-handoff) | evidence.md is a single round table | Worth partial adoption; failure boundary is key for BUG_FIX |
| Search discipline / cost discipline / stop conditions | Absent | Worth absorbing into PROTOCOL.md and/or the scout skill |
| Task-type-specific decision-question patterns | Absent | Worth adding, paired with task_type |

### Proposed landing plan (priority order)

1. Add `task_type` to the `state.yaml` schema (update `STATE_SCHEMA.md`,
   `scripts/ai-workflow/state.py` restricted-YAML handling, and `validate`).
2. Add a `decision-questions.md` template (produced at requirement /
   evidence_collection, question patterns per task_type); scout search scope is
   bounded by the DQ list.
3. Extend the evidence.md template with optional sections: Reproduction,
   Execution Path, Failure Boundary, Contracts, Change Surface — required for
   BUG_FIX.
4. Fold search/cost discipline and stop conditions (condensed from the
   proposal's Prohibited Behavior / Stop Conditions / Cost Discipline sections)
   into PROTOCOL.md and/or the repo-scout skill.

## Open questions

- Does `evidence-audit.md`'s fixed four-question contract need to change if
  evidence.md gains optional sections, or do the sections live "below" the
  audit contract untouched?
- Is a confidence column worth adding to evidence.md, or does
  FACT/INFERENCE/UNKNOWN already carry the needed signal? (Proposal's argument:
  handoff fails when the next model can't tell observed from guessed; the repo
  already answers this with the three tags + anchors.)
- Should decision-questions.md be a separate artifact with its own writer role,
  or a section of evidence.md Round 0?
- The proposal's `ticket.md` Planner output protocol — the repo's plan is
  integrated by reference (`source_artifacts.plan`). Does anything need to
  change there, or is the existing executor-plan contract sufficient?

## Comments

- 2026-10-07 — Document created from conversation: origin of the external
  "Decision Scout" proposal recorded, fit analysis concluded the repo already
  covers the architecture and the valuable increment is operational detail
  (task_type, decision questions, report sections, search discipline). Landing
  plan and open questions captured above.
- 2026-10-07 — The original Chinese chat reply was committed verbatim as
  [original-proposal.md](original-proposal.md) (primary source, for reference
  by downstream agents; do not edit the quoted body). spec.md "Origin" now
  points at it.
- 2026-10-07 — The full fit analysis was committed verbatim as
  [fit-analysis.md](fit-analysis.md) (Chinese body + English analyst working
  notes), for handoff to other models. spec.md "Fit analysis" now points at
  it.
