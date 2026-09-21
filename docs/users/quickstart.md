# 快速上手：走完一个 ticket

本页把一个 ticket 从 `requirement` 走到 `done` 的每一步讲清楚：写什么 artifact、跑什么命令、阶段边界如何提交。以新仓库 + `TICKET-001` 为例。

## 0. 安装

```bash
ai-workflow init --with-skills
```

- 装协议文档 + 模板到 `.ai/workflow/`，在 `AGENTS.md` 追加托管块（原有内容一个字不动）。
- `--with-skills` 顺带把 7 个角色技能装进 `.agents/skills/`（幂等：已最新则跳过，变了才覆盖）。

## 1. 开 ticket

```bash
ai-workflow start TICKET-001 --title "作者信息页 API" \
  --spec docs/specs/spec.md --ticket .scratch/feature/01.md
```

生成 `.ai/work/TICKET-001/`：`state.yaml`（从模板解析填充）+ `evidence.md` / `handoff.md` / `progress.md` 脚手架。`source_artifacts` 按路径引用你的 spec/ticket，**不复制内容**。`decision.md` 留给资深角色，不会伪造。

## 2. 证据收集（evidence_collection）

```bash
ai-workflow advance TICKET-001 --to evidence_collection
```

此刻 `next_action` 指向 `scout`。把仓库事实写进 `evidence.md`，只允许 `FACT` / `INFERENCE` / `UNKNOWN` 三种标签，重要 FACT 带锚点（文件、符号、行、命令、测试结果）。**不允许设计方案**。

> scout 只收集证据，不动 `gate`/`phase`——那些是后面角色的活。

## 3. 证据审计（evidence_audit）

```bash
ai-workflow advance TICKET-001 --to evidence_audit
# 写 evidence-audit.md（只回答四个充分性问题）
ai-workflow set-gate TICKET-001 --gate sufficient --round 1
```

`set-gate` 记录审计结论。`advance` 会根据 gate 自动分叉：

- `sufficient` → 下一步 `technical_decision`
- `insufficient` → 下一步 **`followup_evidence`**（证据不足，回去补）：

```bash
ai-workflow advance TICKET-001 --to followup_evidence   # 回去补证据
ai-workflow advance TICKET-001 --to evidence_audit      # 再审计
ai-workflow set-gate TICKET-001 --gate sufficient --round 2
```

## 4. 技术决策（technical_decision）

```bash
ai-workflow advance TICKET-001 --to technical_decision
```

资深角色写 `decision.md`（方案 / 被否方案 / 不变量 / 兼容性 / API 决策 / 风险 / 升级边界）。写完推进：

```bash
ai-workflow advance TICKET-001 --to planning
```

> 如果此刻 gate 还是 `insufficient`，`advance` 会拒绝并提示——这就是写入时校验。

## 5. 计划（planning）

```bash
ai-workflow advance TICKET-001 --to planning
```

`executor-plan` 把决策拆成有序、每个都能被便宜模型在单步内执行的任务，写进 `progress.md`（或引用 docs 文件），声明任务总数。然后：

```bash
ai-workflow advance TICKET-001 --to implementation
```

任务计数不用你预设——执行者在完成第一个任务时用 `complete-task --total N` 一次性设定。

## 6. 实现（implementation）

```bash
ai-workflow advance TICKET-001 --to implementation
ai-workflow claim TICKET-001 --harness trae --model claude   # 标记本会话在工作
ai-workflow complete-task TICKET-001 --total 3               # 每完成一个任务跑一次
```

`ticket-executor` 每次只做 `current_task` 指的那个任务，完成后 `complete-task` 推进计数，并按任务粒度提交。实现质量层可以交给 Superpowers 的 `tdd` / `verification-before-completion`。

## 7. 评审（review）

```bash
ai-workflow advance TICKET-001 --to review
```

`checkpoint-handoff` 先跑 `ai-workflow validate`（必须无 ERROR），写 `handoff.md`（固定小节 + Repository State 块），然后：

```bash
ai-workflow advance TICKET-001 --to done
```

`advance --to done` 会自动清空 `next_action`（协议要求 done 必须清空）。

## 8. 全程纪律

- **阶段边界提交**：每个阶段结束 `git commit`，前缀固定 `ai-workflow(<ticket-id>): <action>`；实现阶段按任务粒度提交。`git log --grep="ai-workflow("` 能还原整条工作史。
- **validate 在边界把关**：`ai-workflow validate` 无 ERROR 才允许交接；WARN（如未提交的工作、缺失 `updated_at`）记录进 handoff.md。
- **回滚**：出问题 `git revert` 到上一个阶段边界提交，并在 state.yaml 记录 incident 块。

## 快速排查

| 现象 | 原因 |
|---|---|
| `advance` 被拒 "illegal transition" | 转移不在允许表内（STATE_SCHEMA.md） |
| `advance` 被拒 "gate" | 目标阶段要求 `gate=sufficient`，先 `set-gate` |
| `validate` 报 "missing artifact" | 当前阶段要求的 artifact（evidence/audit/decision/handoff）没写 |
| `validate` 报 "missing updated_at" | state.yaml 被手工改过、没走 kit 保存 |
