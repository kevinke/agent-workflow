# Review Findings: Decision Scout and Workflow Handoff

Status: recorded
Type: review-evidence
Date: 2026-10-07

## Scope and provenance

Reviewed the three Decision Scout documents, the existing Workflow Protocol,
role Skills, old ticket feedback, and current CLI source. No separate historical
Agent review document was located; the TRAE analysis is a recorded fit analysis,
not an independent implementation review.

Repository HEAD at inspection:
5ae8e27fb966d00892c4e4b18aa265840a483389.
The working tree already contained counter-consistency edits in mutate/validate
and their tests. Findings below describe that inspected working tree, not a clean
checkout or a newly applied fix. No source edits were made for this review.

## Findings

### R-01 — Evidence reports do not yet carry the desired handoff contract

FACT: the current Evidence template is a round table containing tag, statement,
and anchor. It does not require Decision Question IDs, observation revision,
verification method, verified scope, or a structured planner handoff.

Sources: [Evidence template](../../.ai/workflow/templates/evidence.md:1),
[artifact contract](../../.ai/workflow/ARTIFACTS.md:15).

Consequence: the desired report quality depends on the Scout filling in implicit
requirements. New contract and task-specific examples are the first slice.

### R-02 — The execution Plan is underspecified and its registration is implicit

FACT: executor-plan requires an ordered decomposition and task count, and permits
placing it in Progress. It does not define a per-task scope/acceptance/verification
contract or register the newly written source reference through the CLI.

Sources: [planning Skill](../../.agents/skills/executor-plan/SKILL.md:22),
[completion mutator](../../scripts/ai-workflow/mutate.py:128).

FACT: current_task is incremented on completion, but the executor Skill instructs
the executor to execute current_task. At initial value 0 this is ambiguous.

Source: [executor Skill](../../.agents/skills/ticket-executor/SKILL.md:25).

Consequence: establish a registered, referenced Plan and make the next task
explicit without changing the meaning of completed-task counters.

### R-03 — Review ownership and completion checks are incomplete

FACT: review defaults to checkpoint-handoff, a role whose tier is any. There is
no separate Reviewer role or Review artifact in the current role/artifact lists.

Sources: [default routing](../../scripts/ai-workflow/mutate.py:49),
[role table](../../.ai/workflow/ROLES.md:5),
[artifact table](../../.ai/workflow/ARTIFACTS.md:5).

FACT: advance checks phase edges and Evidence Gate, but not completed registered
tasks or a passing review. The validator checks required artifact presence;
there is no Review verdict gate. A temporary-state probe successfully advanced
an incomplete implementation through review to done without any Review artifact.

Sources: [advance](../../scripts/ai-workflow/mutate.py:78),
[artifact validation](../../scripts/ai-workflow/validate.py:170).

Consequence: separate technical Review from mechanical Handoff and enforce
current pass before done. Retain a deliberate review-to-implementation repair
edge; the current table offers only review-to-done.

### R-04 — Escalation does not apply its documented senior route

FACT: ESCALATION says next_action locks to a senior role. The mutator writes only
the escalation block. The probe retained status=active and
next_action.role=ticket-executor after machine escalation.

Sources: [escalation rule](../../.ai/workflow/ESCALATION.md:22),
[escalation mutator](../../scripts/ai-workflow/mutate.py:182).

Consequence: atomically change route/Status, stop routine completion and advances,
and restore a checked continuation after senior resolution.

### R-05 — Presence checks do not establish content or freshness

FACT: required Evidence/audit/decision checks use file existence. Handoff section
checks use substring presence. The Evidence Gate has no binding to the report
version, and Review has no binding to the code or Plan.

Sources: [validator](../../scripts/ai-workflow/validate.py:170),
[set-gate](../../scripts/ai-workflow/mutate.py:168).

Consequence: check structure and snapshot identity mechanically; leave truth,
unknown significance, and design quality to the relevant senior role.

### R-06 — Stronger contracts need an explicit compatibility path

FACT: upgrade currently overwrites installed protocol files and bumps old Ticket
workflow_version values without checking stronger artifact contracts.

Source: [ticket version bump](../../scripts/ai-workflow/upgrade.py:75).

Consequence: introducing v2 gates needs explicit per-Ticket upgrade, preserved
history, and visible reconstruction blockers rather than an automatic claim that
old work complies. This is a release-design requirement, not a defect in v1's
original same-contract upgrade behavior.

## Reproducible probe

Run from the kit repository. It imports the current mutator and writes only a
temporary directory. It tests mutation behavior; it does not claim that the
full validator accepts missing required v1 artifacts.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path('scripts/ai-workflow').resolve()))
import mutate, state
with tempfile.TemporaryDirectory(prefix='workflow-review-probe-') as root:
    work = Path(root) / '.ai/work/PROBE'
    work.mkdir(parents=True)
    path = work / 'state.yaml'
    data = state.load_file('.ai/workflow/templates/state.yaml')
    data['phase'] = 'implementation'
    data['evidence']['gate'] = 'sufficient'
    data['implementation'] = {
        'current_task': 0, 'total_tasks': 2, 'completed_tasks': []}
    data['next_action'] = {
        'role': 'ticket-executor', 'action': 'implement', 'task': None}
    state.save_file(str(path), data)
    mutate.escalate(root, 'PROBE', scope='machine', reason='design ambiguity')
    current = state.load_file(str(path))
    print(current['status'], current['next_action']['role'])
    print(mutate.advance(root, 'PROBE', 'review'))
    print(state.load_file(str(path))['next_action']['role'])
    print(mutate.advance(root, 'PROBE', 'done'))
PY
```

Observed output on 2026-10-07:

```text
active ticket-executor
PROBE: implementation -> review
checkpoint-handoff
PROBE: review -> done
```

## Assessment of the earlier analysis

Retain its conclusion that the proposal overlaps the repo-native architecture
and should be absorbed incrementally. Its approximate "80%" is an analyst's
estimate, not a measured completion metric. More phases do not establish reliable
handoff. FACT tags and confidence grades address different questions; explicit
verification method and scope are more useful than requiring confidence scores.

The updated spec prioritises inexpensive Scout reports, keeps DQs within Evidence,
defers a task_type State enum, and includes execution/review safeguards as later
vertical slices. The verbatim proposal and fit analysis remain historical sources.

## Comments

- 2026-10-07 — Recorded current source anchors and the temporary probe used in
  the conversation. These findings justify the spec; they are not a claim that
  any of the planned fixes are implemented.
