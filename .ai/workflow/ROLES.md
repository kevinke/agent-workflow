# Roles

Seven roles. Each role has a phase scope and a model tier. Model routing is encoded here: cheap models collect evidence and execute bounded implementation; senior models audit uncertainty, decide, plan, handle escalations, and review.

| Role | Model tier | Phase scope |
|---|---|---|
| scout | cheap | evidence_collection, followup_evidence |
| evidence-auditor | senior | evidence_audit |
| technical-decision | senior | technical_decision |
| executor-plan | senior | planning |
| ticket-executor | cheap | implementation (bounded) |
| checkpoint-handoff | any | phase transitions, handoff |
| workflow-bootstrap | senior | legacy adoption |

Tier names ("cheap" / "senior") are guidance, not harness-specific model mandates. Typical cheap models: DS Flash, GLM Flash. Typical senior models: Terra, Sol. A harness maps these tiers to whatever models it can run.

## scout

- Tier: cheap
- Phase scope: evidence_collection, followup_evidence
- Inputs: state.yaml, ticket and spec source artifacts
- Outputs: evidence.md (FACT / INFERENCE / UNKNOWN + anchors), updated state.yaml
- Rules: collect repository facts only; design proposals are forbidden in evidence.md.

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
- Outputs: implementation plan (referenced from `source_artifacts.plan`), state.yaml phase -> implementation
- Rules: the plan decomposes the decision into ordered tasks; it is integrated by reference, never copied into `.ai/`.

## ticket-executor

- Tier: cheap
- Phase scope: implementation (bounded)
- Inputs: plan, decision.md, evidence.md
- Outputs: code changes, progress.md, state.yaml implementation block updates, per-task commits
- Rules: execute one task at a time; update `current_task` / `completed_tasks`; commit per task with the `ai-workflow(<ticket-id>): <action>` prefix; do not redesign — plan deviation goes to escalation.

## checkpoint-handoff

- Tier: any
- Phase scope: phase transitions, handoff
- Inputs: state.yaml, artifacts
- Outputs: handoff.md, updated state.yaml
- Rules: verify state consistency before a transition; ensure validate-clean before handoff; write handoff.md with the fixed sections and the Repository State block.

## workflow-bootstrap

- Tier: senior
- Phase scope: legacy adoption
- Inputs: an existing repository
- Outputs: migration report, adopted state.yaml with migration / historical_phases / adoption_checkpoint blocks
- Rules: follow MIGRATION.md; never fabricate history; the ticket may not be handed to a cheap executor until `continuation_safe: true`.
