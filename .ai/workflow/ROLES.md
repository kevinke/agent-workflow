# Roles

Eight roles. Each role has a phase scope and a model tier. Model routing is encoded here: cheap models collect evidence and execute bounded implementation; senior models audit uncertainty, decide, plan, handle escalations, and review.

| Role | Model tier | Phase scope |
|---|---|---|
| scout | cheap | evidence_collection, followup_evidence |
| evidence-auditor | senior | evidence_audit |
| technical-decision | senior | technical_decision |
| executor-plan | senior | planning |
| ticket-executor | cheap | implementation (bounded) |
| reviewer | senior (independent context) | review |
| checkpoint-handoff | any | phase transitions, handoff |
| workflow-bootstrap | senior | legacy adoption |

Tier names ("cheap" / "senior") are guidance, not harness-specific model mandates. Typical cheap models: DS Flash, GLM Flash. Typical senior models: Terra, Sol. A harness maps these tiers to whatever models it can run.

## Model routing and continuation

Tiers are Harness-local defaults, not model mandates. The default mapping is cheap models for `scout` and `ticket-executor`, and senior models for `evidence-auditor`, `technical-decision`, `executor-plan`, and `reviewer`. A senior capability may also perform hard scouting or hard implementation when the difficulty warrants it.

- Several logical phases may share one session (for example, a senior session that audits, decides, and plans). The `reviewer` keeps an independent context from the implementation it reviews.
- A receiver continues from persisted state and artifacts, never from chat history: `ai-workflow resume <ticket-id>` prints the read-only continuation brief (next role / action / task, artifact identity and digests, repository state, and continuation checks). Point at reports; do not paste them.
- When the required tools, a reproduction environment, or task clarity are missing, the role escalates (`ai-workflow escalate <ticket-id> --scope machine|human --reason "..."`). Claims stay advisory; this is not model-identity authentication and it assumes no subagent.

## scout

- Tier: cheap
- Phase scope: evidence_collection, followup_evidence
- Inputs: state.yaml, ticket and spec source artifacts
- Outputs: evidence.md (Scout Report: Metadata, Decision Questions, Findings, Unknowns, Handoff — FACT / INFERENCE / UNKNOWN with anchors), updated state.yaml
- Rules: collect repository facts only; design proposals and the evidence verdict are forbidden in evidence.md. Draft DQs when none are supplied; escalate ambiguity requiring an architectural choice; stop when questions are answered or gaps and stopping reason are explicit. A critical UNKNOWN does not open the Evidence Gate — readiness and sufficiency are distinct.

## evidence-auditor

- Tier: senior
- Phase scope: evidence_audit
- Inputs: state.yaml, evidence.md, ticket and spec
- Outputs: evidence-audit.md, `evidence.gate` in state.yaml
- Rules: judge sufficiency; set `gate` to sufficient or insufficient; if insufficient, the next phase is followup_evidence.

## technical-decision

- Tier: senior
- Phase scope: technical_decision
- Inputs: evidence.md, evidence-audit.md
- Outputs: decision.md, state.yaml phase -> planning
- Rules: write the decision: chosen approach, rejected alternatives, invariants, compatibility, API/schema decisions, risks, escalation boundaries.

## executor-plan

- Tier: senior
- Phase scope: planning
- Inputs: decision.md
- Outputs: plan.md (`source_artifacts.plan`), then state.yaml phase -> implementation
- Rules: the plan decomposes the decision into ordered, bounded tasks (`plan.md`); it is integrated by reference, never copied into `.ai/`. On a v2 Ticket register it with `register-plan <ticket-id> --path <plan> --total N`, which stores the path/hash and the ordered task hashes without counting any task complete.

## ticket-executor

- Tier: cheap
- Phase scope: implementation (bounded)
- Inputs: the registered Plan, decision.md, evidence.md
- Outputs: code changes, progress.md, state.yaml implementation block updates, per-task commits
- Rules: execute one registered task at a time; update `current_task` / `completed_tasks`; commit per task with the `ai-workflow(<ticket-id>): <action>` prefix; do not redesign — an executor cannot select or rewrite a registered Plan, so plan deviation goes to escalation.

## reviewer

- Tier: senior default, in an independent context (not the context that wrote the change)
- Phase scope: review
- Inputs: state.yaml, the registered Plan (by reference), decision.md, the actual change and its verification records
- Outputs: reviewer-authored review.md and verdict; the guarded publication step records it via `set-review` in state.yaml.
- Rules: independently verify the acceptance criteria against the actual change and the recorded verification results; record `pass` or `changes_requested`; local repairs stay within the recorded decision and design/architecture changes escalate. On v2, `review -> implementation` is the append-only repair after `changes_requested`; `review -> done` requires a current `pass`. Mechanical checkpoint-handoff cannot supply this verdict. Verification and publication follow PROTOCOL.md §"Reviewer verification isolation and publication"; ARTIFACTS.md owns the provenance contract.

## checkpoint-handoff

- Tier: any
- Phase scope: phase transitions, handoff
- Inputs: state.yaml, artifacts
- Outputs: handoff.md, updated state.yaml
- Rules: mechanical — verify state consistency before a transition; ensure validate-clean before handoff; write handoff.md with the fixed sections and the Repository State block. It supplies no technical verdict: on a v2 Ticket `review` routes to the independent reviewer, not here. It may coordinate guarded publication of the reviewer's exact result under PROTOCOL.md §"Reviewer verification isolation and publication".

## workflow-bootstrap

- Tier: senior
- Phase scope: legacy adoption
- Inputs: an existing repository
- Outputs: migration report, adopted state.yaml with migration / historical_phases / adoption_checkpoint blocks
- Rules: follow MIGRATION.md; never fabricate history; the ticket may not be handed to a cheap executor until `continuation_safe: true`.
