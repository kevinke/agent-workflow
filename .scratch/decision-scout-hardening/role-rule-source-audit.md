# Role rule-source audit (HARDEN-008 Task 1)

Branch `decision-scout-hardening`, 2026-10-09. Built BEFORE thinning: for every
role entry it records the trigger, the authoritative anchors a thinned entry
points at, its command entry, and every copied semantic block found in the
current text with its authoritative home. Nothing is removed silently: each row
either names the existing authoritative home or records the disposition.

Authoritative sources (the only semantic rule homes):

- `.ai/workflow/PROTOCOL.md` — entering a ticket (§3), phase machine (§4),
  claim (§5), scouting/auditing doctrine, registered execution readiness,
  review and completion, counter meaning (§7), escalation overview (§8),
  handoff discipline and portable continuation (§9), commits (§10), adoption
  and version conversion (§11).
- `.ai/workflow/ROLES.md` — role table (tier/phase scope), model routing and
  continuation, per-role inputs/outputs/rules.
- `.ai/workflow/ARTIFACTS.md` — per-artifact contracts (evidence, audit,
  decision, plan, review, progress, handoff), gate binding, transport, export.
- `.ai/workflow/STATE_SCHEMA.md` — state blocks, v2 gate binding / plan
  registration / review binding / escalation fields / upgrade / bootstrap
  recovery / migration blocks.
- `.ai/workflow/ESCALATION.md` — scopes, recording, resolution, v2 atomic
  set/clear and senior recovery.
- `.ai/workflow/MIGRATION.md` — the legacy adoption procedure and its
  non-negotiable rules.
- Public CLI (`scripts/ai-workflow/main.py` USAGE) — the only sanctioned state
  mutations and read-only reports.

## Role Skills

### repo-scout (`.agents/skills/repo-scout/SKILL.md`)

- Trigger (front matter): next_action.role is "scout", or evidence is needed to
  continue a ticket; cheap-model role.
- Command entry: `ai-workflow claim` (session record); handoff via contract;
  NO verdict/advance/set-gate commands.
- Authoritative anchors: ROLES.md §scout; PROTOCOL.md §3 (entering), §5
  (claim), §7 Scouting and auditing, §9 (handoff discipline), §10 (commits);
  ARTIFACTS.md §evidence.md (+ worked examples `.ai/workflow/examples/`).

Copied semantic blocks found BEFORE thinning:

| Copied block (current skill text) | Authoritative home |
|---|---|
| Snapshot doctrine: capture `observed_commit`/`dirty_changes` first | PROTOCOL.md §7 item 1; ARTIFACTS.md §evidence.md Metadata |
| DQ drafting when none supplied + "three to eight is guidance" quota note | PROTOCOL.md §7 item 2; ARTIFACTS.md §Decision Questions |
| FACT/INFERENCE/UNKNOWN, stable F-IDs, anchors, method static/execution/test, scope; negative searches state scope/exclusions | PROTOCOL.md §7 item 3; ARTIFACTS.md §Findings |
| Architectural ambiguity is escalated, not answered | PROTOCOL.md §7 item 2; ROLES.md §scout Rules |
| Temporary diagnostics permitted; record outcome and residual changes | PROTOCOL.md §7 item 6 |
| Stopping rule; exhausted budget yields a partial report, not a verdict | PROTOCOL.md §7 item 5; ROLES.md §scout Rules |
| Design proposals and own sufficiency verdict forbidden; critical UNKNOWN vs gate | ARTIFACTS.md §evidence.md intro and §Unknowns; PROTOCOL.md §7 item 4 |
| Step 7 State-field enumeration (`evidence.round`/`evidence.gate`/`phase`/`next_action`) with set-gate/advance ownership | PROTOCOL.md §7 item 6 ("writes evidence and handoff only"); ROLES.md §scout/§evidence-auditor outputs; STATE_SCHEMA.md §v2 Evidence Gate binding |

Unique real requirements needing a new home: none (examples links are pointers,
not rules).

### evidence-auditor (`.agents/skills/evidence-auditor/SKILL.md`)

- Trigger: next_action.role is "evidence-auditor", or evidence.gate must be
  set; senior-model role.
- Command entry: `ai-workflow claim`, `ai-workflow set-gate --gate --round`;
  NO advance.
- Authoritative anchors: ROLES.md §evidence-auditor; ARTIFACTS.md
  §evidence-audit.md and §Gate binding; STATE_SCHEMA.md §v2 Evidence Gate
  binding; PROTOCOL.md §4 (branches), §7 Scouting and auditing.

| Copied block | Authoritative home |
|---|---|
| Four sufficiency questions only; no recommendations/designs; DQ coverage, traceability, verification limits, decision-changing unknowns | ARTIFACTS.md §evidence-audit.md |
| "Report ready but insufficient when a critical UNKNOWN would change the decision" | ARTIFACTS.md §Unknowns; PROTOCOL.md §7 item 4 |
| "Recorded verdict binds to the audited artifacts; if either changes, re-audit and re-run set-gate" | ARTIFACTS.md §Gate binding (workflow_version 2); STATE_SCHEMA.md §v2 Evidence Gate binding |
| Advance branch destinations (sufficient → technical_decision, insufficient → followup_evidence) | PROTOCOL.md §4 |

Unique real requirements: none.

### technical-decision (`.agents/skills/technical-decision/SKILL.md`)

- Trigger: next_action.role is "technical-decision" and gate is sufficient;
  senior only.
- Command entry: `ai-workflow claim`, `ai-workflow advance --to planning`.
- Authoritative anchors: ROLES.md §technical-decision; ARTIFACTS.md
  §decision.md; PROTOCOL.md §7, §9, §10; ESCALATION.md.

| Copied block | Authoritative home |
|---|---|
| decision.md content list (chosen approach, rejected alternatives, invariants, compatibility, API/schema, risks, escalation boundaries) | ARTIFACTS.md §decision.md |
| "Leave nothing undecided that the plan needs" | ARTIFACTS.md §decision.md forbidden set ("undecided design questions") |
| Advance enforces the gate and routes to executor-plan | PROTOCOL.md §4, §7; STATE_SCHEMA.md §Phases |

Unique real requirements: none.

### executor-plan (`.agents/skills/executor-plan/SKILL.md`)

- Trigger: next_action.role is "executor-plan"; senior only.
- Command entry: `ai-workflow claim`, `ai-workflow register-plan --path
  --total` (v2), `ai-workflow advance --to implementation`.
- Authoritative anchors: ROLES.md §executor-plan; ARTIFACTS.md §plan.md;
  STATE_SCHEMA.md §v2 Plan registration; PROTOCOL.md §7, §10.

| Copied block | Authoritative home |
|---|---|
| Task-section list (objective, inputs, allowed/protected scope, invariants, acceptance criteria, verification, dependencies, escalation conditions) | ARTIFACTS.md §plan.md |
| Registration stores path/hash + ordered task hashes, counts nothing complete | ARTIFACTS.md §plan.md; STATE_SCHEMA.md §v2 Plan registration; ROLES.md §executor-plan |
| "On a v1 Ticket skip this step and record the task count in `progress.md` instead" — DRIFT, removed: no contract says this, and the v1 CLI supplies the total at completion time (`complete-task --total N`; the CLI rejects completion with `total_tasks=0 (set --total N first)`). The authoritative v1 fact is non-registration: "A v1 Ticket ... is rejected" (STATE_SCHEMA.md §v2 Plan registration); the completed-count counter meaning is PROTOCOL.md §Counter meaning (both versions) | Disposition recorded here (not silent); replacement prose only states the authoritative v2/v1 registration split |

Unique real requirements: none beyond the drift disposition above.

### ticket-executor (`.agents/skills/ticket-executor/SKILL.md`)

- Trigger: next_action.role is "ticket-executor" during implementation; cheap
  role.
- Command entry: `ai-workflow claim`, `ai-workflow complete-task`; NO
  advance/set-review/plan rewriting.
- Authoritative anchors: ROLES.md §ticket-executor; PROTOCOL.md §7 Registered
  execution readiness + Counter meaning + Review and completion; ARTIFACTS.md
  §progress.md and templates/progress.md; ESCALATION.md.

| Copied block | Authoritative home |
|---|---|
| "next_action.task is the completed count plus one" | PROTOCOL.md §Counter meaning (both versions) |
| v2 completion preconditions (registered unchanged Plan, `--total` cannot override, rejection leaves State untouched) | PROTOCOL.md §7 Registered execution readiness; STATE_SCHEMA.md §v2 Plan registration |
| progress.md content list (actual changes, verification/result, deviation, unresolved problems; not every shell command) | ARTIFACTS.md §progress.md; `.ai/workflow/templates/progress.md` |
| "Repair path" section (append-only rework, verdict cleared to pending, completed prefix preserved, no redesign, escalate design changes) | PROTOCOL.md §7 Review and completion; ESCALATION.md §Recording |
| Role boundary tail (no decision.md writes, advance belongs to checkpoint-handoff) | ROLES.md §ticket-executor/§checkpoint-handoff; PROTOCOL.md §7 |

Unique real requirements: none.

### reviewer (`.agents/skills/reviewer/SKILL.md`)

- Trigger: next_action.role is "reviewer", or a Review verdict must be
  recorded; senior default, independent context.
- Command entry: `ai-workflow claim`, `ai-workflow set-review --verdict`; NO
  advance.
- Authoritative anchors: ROLES.md §reviewer; ARTIFACTS.md §review.md;
  STATE_SCHEMA.md §v2 Review binding; PROTOCOL.md §7 Review and completion;
  ESCALATION.md.

| Copied block | Authoritative home |
|---|---|
| Independent-context requirement | ROLES.md §reviewer; ARTIFACTS.md §review.md intro |
| "Independently verify acceptance criteria against the actual change and recorded verification results" | ROLES.md §reviewer Rules; ARTIFACTS.md §review.md |
| review.md content list (reviewed commit, Plan identity, acceptance/verification results, findings, verdict, required rework) | ARTIFACTS.md §review.md Required sections |
| Verdict binding (artifact bytes, reviewed commit, registered Plan; re-review on change) | ARTIFACTS.md §review.md; STATE_SCHEMA.md §v2 Review binding |
| Append-only rework path; local repairs vs design/architecture escalation | PROTOCOL.md §7 Review and completion; ESCALATION.md |
| "review -> done requires a current pass"; checkpoint-handoff performs transitions | PROTOCOL.md §7 Review and completion; ROLES.md §checkpoint-handoff |

Unique real requirements: none.

### checkpoint-handoff (`.agents/skills/checkpoint-handoff/SKILL.md`)

- Trigger: next_action.role is "checkpoint-handoff", or a phase transition or
  handoff is due; any tier.
- Command entry: `ai-workflow validate`, `ai-workflow claim`, `ai-workflow
  advance --to <phase>`, `ai-workflow escalate --clear --resolution` (v2),
  `ai-workflow resume`.
- Authoritative anchors: ROLES.md §checkpoint-handoff; PROTOCOL.md §4, §7
  Review and completion, §9 Handoff discipline + Portable continuation;
  STATE_SCHEMA.md §Phases; ESCALATION.md §Resolution and §Clearing;
  ARTIFACTS.md §handoff.md.

| Copied block | Authoritative home |
|---|---|
| Escalation-clear rules (senior resolution text with supporting reference; human scope needs the user's answer; missing/unreferenced resolution rejected; v1 keeps bare clear) | ESCALATION.md §Resolution and §Clearing (v2 atomic escalation) |
| Advance mechanics (enforces transition + gate, points next_action, clears at done; rejection means not ready) | PROTOCOL.md §4, §7; STATE_SCHEMA.md §Phases |
| Role-boundary section (review routes to independent reviewer; `advance --to done` requires current `pass`; review→implementation is the append-only repair) | PROTOCOL.md §7 Review and completion; ROLES.md §checkpoint-handoff/§reviewer |
| Resume brief description | PROTOCOL.md §9 Portable continuation |

Unique real requirements: none.

### workflow-bootstrap (`.agents/skills/workflow-bootstrap/SKILL.md`)

- Trigger: adopting an existing/legacy repo or a half-done ticket; senior
  role.
- Command entry: `ai-workflow adopt` (mechanical steps), `ai-workflow advance
  --to <phase>` after checkpoint, `ai-workflow validate`.
- Authoritative anchors: MIGRATION.md (whole procedure + "Rules that never
  bend"); STATE_SCHEMA.md §Migration blocks (adoption_checkpoint);
  PROTOCOL.md §11.

| Copied block | Authoritative home |
|---|---|
| Procedure summary (discovery, migration report, phase reconstruction, retroactive minimum evidence, decision reconstruction, adoption checkpoint) | MIGRATION.md §Procedure |
| "Never fabricate / never re-walk history / integrate by reference / continuation_safe gates cheap executors" | MIGRATION.md §Rules that never bend and §6 Adoption checkpoint |
| Six checkpoint item names | MIGRATION.md §6; STATE_SCHEMA.md §adoption_checkpoint |
| "No CLI command yet: confirm the six items and set `continuation_safe: true` by hand" — kept as an operational note (verified against the current CLI: `adopt` scaffolds them false and no command mutates them); the authoritative field contract is MIGRATION.md §6 + STATE_SCHEMA.md §adoption_checkpoint | Operational, not a rule copy |

Unique real requirements: none.

## Adapters

### `adapters/trae/project_rules.md`

- Copied block: model-tier mapping ("Scout and executor cheap; auditor,
  decision, planner, Reviewer senior"), senior-may-do-hard-work, decision
  phases share a session, review stays independent, escalate on missing
  tools/environment — duplicates ROLES.md §Model routing and continuation.
- Home: ROLES.md. Thin to a pointer; keep the operational pointers (read
  PROTOCOL, state.yaml first, resume recipe, write back before stopping).

### `scripts/ai-workflow/init.py` MANAGED_BLOCK (AGENTS.md managed entry)

- Copied block: second paragraph's tier mapping, senior-hard-work allowance,
  shared decision sessions, independent review, escalate-on-missing-tools —
  duplicates ROLES.md §Model routing and continuation.
- Home: ROLES.md. Thin to a pointer; keep state-first operational pointer and
  the `ai-workflow resume` recipe (PROTOCOL.md §9 Portable continuation).
- Constraints honored: test_init.py locks only markers/idempotence/user-byte
  preservation, so the wording change stays test-covered.

## Windows runbook (new `adapters/codex/windows.md`)

No semantic rule copies. It cites the pilot's observed rejection and fix
(`.scratch/decision-scout-port/pilot/report.md` — the `CreateProcess …
rejected: blocked by policy` block and the per-session `-c
windows.sandbox="unelevated"` launch setting; raw logs under
`.scratch/decision-scout-port/pilot/logs/`), documents cost-free
`codex --version` / `codex exec --help` collection, distinguishes
launch/policy rejection from model findings, records host/build variance,
permission preservation, bounded read-only diagnostics before interpreting
review logs, stop-on-rejection (no auto-retries, no global config edits, no
sandbox downgrade), and a separately-budgeted implementation-time smoke
session whose prompt performs one read-only repository command and reports
policy refusal separately.

## Result

After thinning, every contract has exactly one semantic home (PROTOCOL /
ROLES / ARTIFACTS / STATE_SCHEMA / ESCALATION / MIGRATION); the eight Skills
and both adapter entries carry triggers, authoritative links, and minimal
command recipes only. One drifted instruction (executor-plan's v1
"task count in progress.md" note) is removed with its disposition recorded in
the table above instead of an invented rule.
