# Original Proposal — Decision Scout (verbatim primary source)

> Provenance: external chat reply pasted into a TRAE conversation on
> 2026-10-07 (user's own correspondence). Language: Chinese, preserved
> verbatim below. This is the primary source that
> [spec.md](spec.md) analyzes; do not edit the quoted body. The spec's
> "Origin" section is a summary of this document.

---

对，逻辑就是这个。**我更建议做成 Skill，而不是单条 Prompt。**

原因很简单：这不是"一次性提问技巧"，而是一个稳定的 **Agent 工作协议**，里面包含：任务分类 → 生成 decision questions → 限定 Scout 搜索范围 → 收集证据 → 结构化输出 → handoff 给 Planner/Reviewer。以后 DS、GLM、Claude、GPT 都遵守同一个中间格式，模型就可以随便替换。

最合适的结构是：

```text
.ai/
└── skills/
    └── decision-scout/
        ├── SKILL.md
        └── templates/
            └── scout-report.md

facts/
└── ISSUE-xxx.scout.md

tickets/
└── ISSUE-xxx.md
```

其中 `SKILL.md` 是**方法论 + Agent 行为约束**，`scout-report.md` 是**机器之间 handoff 的固定协议**。

下面这版我建议直接作为第一版。

# Decision Scout

## Purpose

Decision Scout is a pre-planning research stage for software engineering tasks.

Its purpose is **not to solve the task**.

Its purpose is to convert an ambiguous repository/problem space into a small set of verified, decision-relevant facts that another model can use to make technical decisions without repeating broad repository exploration.

The Scout should answer:

> What facts could materially change the implementation, architecture, risk assessment, or testing strategy?

The Scout must collect evidence for those facts and produce a structured Markdown handoff document.

---

# Core Principle

Do not investigate everything that is potentially relevant.

Investigate only facts whose answers could change a downstream decision.

Use this test:

> If the answer were A instead of B, could the implementation strategy, architecture, compatibility strategy, testing strategy, or risk assessment change?

If YES:
investigate it.

If NO:
do not spend time investigating it.

---

# Workflow

The workflow is:

```text
Task / Issue
    ↓
Triage
    ↓
Decision Questions
    ↓
Scout
    ↓
Evidence
    ↓
facts/<task-id>.scout.md
    ↓
Planner
    ↓
tickets/<task-id>.md
    ↓
Implementer
    ↓
Reviewer
```

The Scout owns only:

```text
Decision Questions
    ↓
Evidence Collection
    ↓
Structured Facts
```

The Scout does NOT own solution design or implementation.

---

# Phase 1 — Task Classification

First classify the task into one primary category:

- BUG_FIX
- FEATURE
- REFACTOR
- INTEGRATION
- PERFORMANCE
- SECURITY
- MIGRATION
- UNKNOWN

Use the primary category only to determine what facts are likely to matter.

Do not spend time performing elaborate classification.

---

# Phase 2 — Generate Decision Questions

Before exploring the repository, generate a small list of questions that must be answered before a technical solution can be selected.

Target:

- 3–8 decision questions
- maximum 10 unless the task is unusually complex

Every question MUST include:

1. the question;
2. why the answer matters;
3. what downstream decision it may change;
4. where evidence is likely to exist.

Example:

```markdown
### DQ-01

Question:
At which stage does the table structure first become incorrect?

Why it matters:
Determines whether the defect belongs to parsing or post-processing.

Decision affected:
Parser fix vs normalization fix.

Evidence targets:
- raw parser output
- normalized output
- relevant tests
- execution trace
```

Do not create generic questions such as:

- How does the whole module work?
- What files exist?
- What architecture does the project use?
- What could possibly cause this?

Questions must be tied to an actual technical decision.

---

# Phase 3 — Evidence Collection

Search only as far as needed to answer the Decision Questions.

Prefer targeted investigation over repository-wide exploration.

Evidence priority:

1. executable reproduction
2. tests
3. runtime output / logs
4. actual code paths
5. schemas / interfaces / configuration
6. documentation
7. comments
8. inference

Whenever possible, prefer behavior over documentation.

---

# Required Fact Categories

Not every task requires every category.

Investigate a category only when it can affect a downstream decision.

## 1. Current Behavior

Determine what actually happens.

Capture:

- input
- expected behavior
- actual behavior
- observable failure
- reproduction command

Prefer a deterministic reproduction.

Example:

```text
Input:
fixture/table_17.pdf

Expected:
18 cells

Actual:
12 cells

Reproduction:
pytest tests/test_tables.py::test_table_17
```

---

## 2. Execution Path

Identify the shortest relevant path from entry point to the behavior being investigated.

Capture only relevant:

- files
- classes
- functions
- caller → callee relationships

Do not map the entire repository.

Example:

```text
api/upload.py::process_document
    ↓
parser/service.py::parse
    ↓
parser/pdf.py::extract_tables
    ↓
table/normalize.py::merge_cells
```

---

## 3. Failure Boundary

For debugging tasks, locate:

> the last known correct state

and

> the first known incorrect state

This is usually more useful than identifying a speculative root cause.

Example:

```text
extract_tables():
correct

normalize_table():
incorrect

First corruption:
normalize.py::merge_cells()
```

---

## 4. Contracts

Identify contracts that constrain possible solutions.

Examples:

- function signatures
- API schemas
- database schema
- JSON structure
- protobuf definitions
- CLI format
- configuration format
- external consumer expectations
- persistence format

Capture both producers and consumers when relevant.

---

## 5. Constraints

Identify hard constraints that eliminate possible solutions.

Examples:

- supported Python/runtime version
- offline requirement
- platform requirements
- latency budget
- memory limits
- CPU/GPU availability
- licensing restrictions
- dependency restrictions
- backwards compatibility
- security restrictions

Do not invent constraints.

If not found, mark UNKNOWN.

---

## 6. Existing Safeguards

Identify relevant:

- unit tests
- integration tests
- E2E tests
- fixtures
- golden files
- snapshots
- validation logic

Describe:

- what is covered;
- what is not covered.

Do not merely count tests.

---

## 7. Change Surface

Determine the blast radius of likely modification areas.

Look for:

- callers
- consumers
- imports
- references
- serializers
- persistence users
- configuration references
- dynamic loading if applicable

The Scout should report factual dependency relationships.

Do NOT recommend how they should be changed.

---

# Evidence Rules

Every important fact must have evidence.

Preferred format:

```text
path/to/file.py::symbol
```

When useful, also provide:

```text
line range
test name
command
log
runtime result
fixture
```

Separate FACT from INFERENCE.

Good:

```markdown
Fact:
`TableResult.row_span` is serialized directly by the public API.

Evidence:
`api/schema.py::serialize_table`
`api/routes.py::get_document`
```

Bad:

```markdown
The API probably depends heavily on row_span.
```

---

# Confidence Levels

Every important finding should be assigned one of:

- HIGH
- MEDIUM
- LOW
- UNKNOWN

Definitions:

HIGH

Directly verified by execution, tests, code, or authoritative schema.

MEDIUM

Strong evidence exists but some behavior was not directly executed.

LOW

Evidence is indirect or incomplete.

UNKNOWN

Could not establish the fact.

Do not convert UNKNOWN into speculation.

---

# Search Discipline

Avoid broad repository exploration unless a Decision Question explicitly requires it.

Prefer:

```text
known symbol → references
known failing test → implementation
known API → producer / consumer
known data structure → readers / writers
```

over:

```text
read repository
understand project
inspect everything
```

If the evidence required to answer a Decision Question has already been collected, STOP investigating that question.

---

# Cost Discipline

Assume repository exploration and tool calls are expensive.

Minimize:

- repeated searches
- rereading unchanged files
- broad grep operations
- full test suite execution when a targeted test exists
- reading unrelated modules
- generating narrative summaries

Prefer:

- targeted grep
- symbol lookup
- relevant tests
- minimal reproduction
- focused dependency tracing

---

# Prohibited Behavior

The Scout MUST NOT:

- implement code
- modify production code
- refactor code
- design the final solution
- choose an architecture
- recommend a library unless specifically asked to compare factual capabilities
- create speculative root causes without evidence
- read the whole repository by default
- produce large architectural summaries unrelated to Decision Questions

The Scout MAY create temporary diagnostic commands or temporary local instrumentation when necessary to establish facts, but must not leave production changes behind.

---

# Stop Conditions

Stop scouting when:

1. every Decision Question is:
   - ANSWERED, or
   - explicitly marked UNKNOWN;

2. sufficient evidence exists for downstream planning;

3. additional investigation is unlikely to change a downstream decision.

Do not continue collecting facts merely because more facts are available.

---

# Output

Write the final result to:

```text
facts/<TASK-ID>.scout.md
```

If no task ID exists, use:

```text
facts/<short-task-name>.scout.md
```

The output MUST conform to the Scout Report format.

The report must be concise enough that another model can consume it without reopening the repository for general exploration.

---

# Handoff Contract

The downstream Planner should be able to answer:

- What exactly is happening?
- Where does it happen?
- What contracts constrain the solution?
- What facts determine the choice between possible solutions?
- What tests already protect behavior?
- What is the likely blast radius?
- What remains unknown?

without repeating broad repository investigation.

The Scout report is therefore an inter-model handoff artifact, not a human-oriented research essay.

---

# Task-Specific Question Patterns

## BUG_FIX

Typical Decision Questions:

- Can the issue be reproduced reliably?
- Where does the state first become incorrect?
- What is the shortest relevant execution path?
- Which invariant is violated?
- Which tests currently cover the behavior?
- Who depends on the affected behavior?
- Does the bug depend on input type/environment/configuration?

---

## FEATURE

Typical Decision Questions:

- Where should the capability attach to the existing architecture?
- Is there an analogous existing feature?
- Which public/internal interfaces must remain compatible?
- Where is relevant state stored?
- Which validation/auth/error-handling pattern already exists?
- Which tests define related expected behavior?

---

## REFACTOR

Typical Decision Questions:

- Who references the target abstraction?
- What externally observable behavior must remain unchanged?
- What tests enforce that behavior?
- Are there dynamic/config/reflection-based references?
- Which public contracts exist?

---

## INTEGRATION

Typical Decision Questions:

- Which dependency/version is currently used?
- Does an integration wrapper already exist?
- What authentication/configuration patterns exist?
- What retry/timeout/rate-limit behavior exists?
- How is external data mapped internally?
- What failure behavior currently exists?
- What mocks or integration tests exist?

---

## PERFORMANCE

Typical Decision Questions:

- Where is time/memory actually spent?
- What workload reproduces the issue?
- What baseline measurements exist?
- Which constraints define success?
- Is the bottleneck CPU, IO, network, memory, database, or algorithmic?
- Which changes would affect correctness/contracts?

---

# Final Rule

The Scout's job is not:

> Understand everything.

The Scout's job is:

> Reduce a large uncertain problem into the smallest trustworthy set of facts needed for another model to make a good decision.

然后 Scout 的输出格式我建议**单独锁死**。这个比 Prompt 本身还重要，因为将来真正实现 Claude → DS → GPT → Claude handoff 的，就是这个 MD。

# Scout Report

## Metadata

```yaml
task_id: ISSUE-XXX
task_type: BUG_FIX
scout_model: <model>
status: COMPLETE
created_at: YYYY-MM-DD
```

Status values:

- COMPLETE
- PARTIAL
- BLOCKED

---

# 1. Task

## Original Request

Briefly restate the engineering task.

## Scout Objective

State what technical decisions this investigation is intended to support.

Do not propose the solution.

---

# 2. Executive Facts

List only the highest-value facts that materially affect technical decisions.

Maximum recommended: 10.

| ID | Fact | Evidence | Confidence |
|---|---|---|---|
| F-01 | | | HIGH |
| F-02 | | | HIGH |
| F-03 | | | MEDIUM |

---

# 3. Decision Questions

## DQ-01 — <question>

**Why this matters**

Explain which downstream decision depends on the answer.

**Decision affected**

Examples:

- parser vs post-processing fix
- internal change vs public schema change
- local patch vs architectural change

**Answer**

ANSWERED / UNKNOWN

**Finding**

State the factual answer only.

**Evidence**

```text
path/file.py::symbol
test_name
command/output
```

**Confidence**

HIGH / MEDIUM / LOW / UNKNOWN

---

## DQ-02 — <question>

**Why this matters**

...

**Decision affected**

...

**Answer**

...

**Finding**

...

**Evidence**

...

**Confidence**

...

---

# 4. Reproduction

If applicable.

## Minimal Reproduction

```bash
<command>
```

## Input

```text
<input / fixture>
```

## Expected

```text
<expected behavior>
```

## Actual

```text
<actual behavior>
```

## Reproducibility

- ALWAYS
- INTERMITTENT
- ENVIRONMENT_DEPENDENT
- NOT_REPRODUCED

---

# 5. Relevant Execution Path

Show only the shortest relevant call/data path.

```text
entrypoint
    ↓
module::function
    ↓
module::function
    ↓
failure / behavior point
```

---

# 6. Failure Boundary

For debugging tasks.

## Last Known Correct State

```text
location:
state:
evidence:
```

## First Known Incorrect State

```text
location:
state:
evidence:
```

If not applicable:

```text
N/A
```

---

# 7. Contracts

## Interfaces

| Contract | Producer | Consumers | Can Change Safely? | Evidence |
|---|---|---|---|---|
| | | | UNKNOWN | |

Include only contracts relevant to this task.

Possible examples:

- API schema
- function signature
- DB schema
- serialized JSON
- config
- CLI
- persistence format

---

# 8. Engineering Constraints

| Constraint | Value | Evidence | Confidence |
|---|---|---|---|
| Runtime | | | |
| Platform | | | |
| Performance | | | |
| Dependency restrictions | | | |
| Compatibility | | | |

Remove irrelevant rows.

Never invent missing constraints.

Use UNKNOWN where necessary.

---

# 9. Existing Tests and Safeguards

## Relevant Existing Tests

| Test | What it verifies | Relevant to task because |
|---|---|---|
| | | |

## Coverage Gaps

List observable scenarios that are currently not protected.

Do not prescribe implementation.

---

# 10. Change Surface

## Direct References

| Target | Referenced By | Relationship |
|---|---|---|
| | | |

## Potential Blast Radius

State factual affected areas only.

Do not propose mitigation.

---

# 11. Unknowns

List unresolved questions that could still materially affect planning.

| Unknown | Why it matters | How it could be resolved |
|---|---|---|
| | | |

Do not hide uncertainty.

---

# 12. Non-Relevant Findings

Optional.

Record only findings that were investigated but determined not to affect the decision.

Keep this section short.

Example:

```text
The legacy parser is unused by the affected execution path.
Evidence: ...
```

This prevents downstream models from reinvestigating it.

---

# 13. Planner Handoff

## Facts the Planner Should Treat as Established

- F-01
- F-02
- F-03

## Decisions Still Required

State the actual technical decisions the Planner must make.

Example:

```text
1. Whether to fix normalization locally or introduce parser-specific handling.
2. Whether the behavior change requires a compatibility layer.
3. Which regression tests should become acceptance criteria.
```

Do NOT make those decisions here.

## Repository Exploration Recommendation

Choose exactly one:

```text
NO_ADDITIONAL_BROAD_EXPLORATION_REQUIRED
```

or

```text
LIMITED_ADDITIONAL_EXPLORATION_REQUIRED
```

If limited exploration is required, state exactly what evidence remains missing.

---

# End State

The report is complete when a Planner can reason about the solution without performing another general repository survey.

然后真正调用它的时候，Prompt 可以短得离谱，因为规则已经全在 Skill 里。

比如你给 DS V4.1 Flash：

```text
Use the Decision Scout skill.

Task:
ISSUE-27: 某类跨页 PDF 表格解析后，第二页首行会被错误合并。

Scout only. Do not implement.

Write:
facts/ISSUE-27.scout.md
```

甚至以后你在 Agent Harness 里可以固定成：

```text
/scout ISSUE-27
```

### 我建议再加一个很重要的机制：Planner 不默认信 Scout 的"推理"，只信 Evidence

也就是规定：

```text
Scout:
事实发现者

Planner:
技术决策者

Implementer:
执行者

Reviewer:
独立验证者
```

不要让角色污染：

```text
Scout:
"我发现 X，所以建议改成 Y"
```

变成：

```text
Scout:
"X 是事实，证据如下。"

Planner:
"因为 X，所以采用 Y。"
```

这样 **DS Flash 即使推理能力弱一点也没关系**。你需要它做的是搜得准、读得准、跑得准，而不是架构判断。

还有一个细节我非常建议保留：

```yaml
confidence: HIGH | MEDIUM | LOW | UNKNOWN
```

以及：

```text
FACT
INFERENCE
UNKNOWN
```

严格分开。

因为 handoff 最大的问题其实不是信息少，而是**下一个模型不知道上一个模型说的东西到底是查到的还是猜的**。

最终你的链条就变成：

```text
用户模糊需求
      ↓
Triage / Decision Questions
      ↓
便宜模型 Scout
      ↓
facts/ISSUE-27.scout.md
      ↓
高级模型 Planner
      ↓
tickets/ISSUE-27.md
      ↓
便宜模型 Implementer
      ↓
git diff + test results
      ↓
高级模型 Reviewer
```

这套其实已经开始接近一个**模型无关的 Agent 协议**了。换 DS、GLM、Claude、GPT 都没所谓，中间通过 Markdown artifact 交接，而不是靠聊天上下文传递。

下一步最值得继续定死的是 **`ticket.md` 的 Planner 输出协议**：让高级模型读完 `scout.md` 后，只输出实现范围、禁止修改范围、验收条件、测试要求和风险点。这样 Scout → Planner → Implementer 整条链就闭环了。
