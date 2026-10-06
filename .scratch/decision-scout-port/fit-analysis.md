# Fit Analysis — Decision Scout vs. agent-workflow (verbatim record)

> Provenance: analysis produced in a TRAE conversation on 2026-10-07, after
> reading the repo's protocol layer (`.ai/workflow/`, `.agents/skills/`,
> `docs/adr/`, `docs/agents/`). Language: Chinese, preserved verbatim below
> as a primary-source record for handoff to other models. The spec's
> "Fit analysis" / "Proposed landing plan" sections are a condensed
> English summary of this document. Do not edit the quoted body.

---

分析完了。结论先说：**这套东西和仓库现有的协议高度重合——仓库本身就已经是这套协议的"更严格版"。所以问题不是"怎么加入"，而是"吸收它多出来的那部分增量"。**

## 一、仓库里已经有什么

这个仓库（agent-workflow）已经实现了一个 repo-native 的跨 harness Agent 工作流协议，和回复里的提案是同一个思路：

- **角色隔离已经存在**：ROLES.md 定义了七个角色，其中 scout 是 cheap 模型、只负责 evidence_collection，technical-decision 和 executor-plan 是 senior 模型——正是提案里"便宜模型搜事实、贵模型做决策"的模型分层路由。
- **FACT/INFERENCE/UNKNOWN 已经存在**：evidence.md 模板和 ARTIFACTS.md 规定 scout 只写带锚点的事实，**明确禁止 design proposals**——这就是提案强调的"Planner 不默认信 Scout 的推理"。
- **甚至证据审查门已经存在**：evidence-auditor（senior）只做充分性判断、set gate——这比提案更进一步，提案里没有 audit 环节。
- **handoff 契约已经存在**：handoff.md 固定章节里的 "Do not repeat" 就对应提案的 Non-Relevant Findings。

## 二、提案多出来、仓库没有的增量

| 提案内容 | 仓库现状 | 价值评估 |
|---|---|---|
| 任务分类（BUG_FIX/FEATURE/...） | `state.yaml` 无 task_type 字段 | 值得加，且能驱动下面的分类问题模板 |
| Decision Questions（3~8 个结构化问题驱动搜索） | scout 直接收集证据，没有结构化问题层 | **最有价值的增量**，正好解决"限定 cheap 模型搜索范围" |
| 置信度（HIGH/MEDIUM/LOW/UNKNOWN） | 只有 FACT/INFERENCE/UNKNOWN 三态 | 半冗余——FACT 本身已隐含"已验证"。可以考虑加，但非必需 |
| 富 Scout Report 模板（复现/执行路径/失败边界/契约/约束/影响面/Planner Handoff） | evidence.md 只有一张 Round 表格 | 值得部分吸收，尤其 BUG_FIX 的 failure boundary |
| 搜索纪律/成本纪律/停止条件 | 无 | 值得吸收，适合放进 PROTOCOL 或 scout skill |
| task-specific 问题模式 | 无 | 值得加，和任务分类配套 |

## 三、一个必须注意的架构冲突

提案说"方法论写进 `SKILL.md`"，但这违反本仓库的 ADR 0001 的核心决策：**业务规则放 repo 里的 `.ai/workflow/`，skill 只是薄适配层**。现有 repo-scout/SKILL.md 就是刻意设计成"thin operational procedure"，明确写着 "All business rules live in the protocol... Do not restate protocol rules here"。

所以如果要吸收提案内容，正确姿势是：

1. **方法论 →** `.ai/workflow/`（PROTOCOL.md 增补 + 新模板文件）
2. **Skill 只加一两行指针**，保持薄

## 四、建议的落地方案（按优先级）

1. **`state.yaml` 加 `task_type` 字段**（需同步改 STATE_SCHEMA.md、`scripts/ai-workflow/state.py` 的受限 YAML 解析和 validate）
2. **新增 `decision-questions.md` 模板**（requirement/evidence_collection 阶段产出，按任务类型给问题模式），scout 的搜索范围由 DQ 列表限定——这是提案对现有协议最实质的增强
3. **evidence.md 模板增加可选章节**：Reproduction / Execution Path / Failure Boundary / Contracts / Change Surface，BUG_FIX 类任务必填
4. **scout skill / PROTOCOL 增补搜索纪律与停止条件**（提案里 Prohibited Behavior、Stop Conditions、Cost Discipline 三节，措辞精简后并入）

## 五、结论

**合适，但定位要摆正**：这不是引入一套新东西，而是给现有协议补上"任务分类 + 决策问题驱动 + 结构化报告章节 + 搜索纪律"四块操作层细节。架构层面仓库已经更完整（多了 audit gate、claim 机制、状态机、rollback），不需要从提案搬任何东西。

---

## Analyst's working notes (English, same session)

Raw key findings behind the analysis above, kept for the receiving model:

1. The repo ALREADY implements ~80% of the proposal: repo-native protocol,
   seven roles (scout cheap / senior decision/planner), FACT/INFERENCE/UNKNOWN
   + anchors, evidence-audit gate, decision.md senior-only, handoff contract,
   model-agnostic via state.yaml.
2. Overlaps in detail: role isolation ("Scout = fact-finder, Planner =
   decision-maker") already in ROLES.md; FACT vs INFERENCE separation already
   in the evidence.md contract; the evidence-auditor role serves exactly the
   proposal's "Planner doesn't trust Scout reasoning" mechanism.
3. Mapping between the proposal's layout and this repo:
   `facts/ISSUE-xxx.scout.md` -> `.ai/work/<ticket-id>/evidence.md`;
   `tickets/ISSUE-xxx.md` -> plan integrated by reference
   (`source_artifacts.plan`); the proposal's Triage -> DQ -> Scout -> Planner
   -> Implementer -> Reviewer pipeline maps onto the repo's phase machine,
   which is strictly richer (evidence loop, claim semantics, rollback).
4. Port candidates, with cautions:
   a. Decision Questions as a structured artifact — either a Round-0 section
      of evidence.md or a new `.ai/workflow/templates/decision-questions.md`;
      bounds cheap-scout search scope.
   b. Richer evidence.md sections (reproduction, execution path, failure
      boundary, contracts, constraints, change surface) — must not break
      evidence-audit.md's fixed four-question contract; safest as optional
      sections required for BUG_FIX.
   c. task_type in state.yaml — requires updating STATE_SCHEMA.md, the
      restricted-YAML parser (ADR-0002 subset), and validate.
   d. Confidence grading — likely redundant with FACT/INFERENCE/UNKNOWN; a
      deliberate decision either way should be recorded.
   e. Search/cost discipline + stop conditions — condensed into PROTOCOL.md
      and/or the repo-scout skill.
   f. "Repository exploration recommendation" (NO_ADDITIONAL_BROAD_EXPLORATION
      / LIMITED_...) — largely covered by handoff.md's existing "Do not
      repeat" and "Next recommended action" sections.
