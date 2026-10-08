# 在已有仓库使用（adopt 迁移 + Matt / Superpowers 集成）

一个已经存在的仓库，可能带着 Matt / Superpowers 的痕迹（有 `AGENTS.md`、`CONTEXT.md`、`.scratch/` 票据、GitHub Issues、CLAUDE.md 等）。本页讲怎么把它接进 agent-workflow，以及三层技能怎么配合。

## 分层分工（先对齐心智模型）

| 层 | 管什么 | 谁产出 | 接进 kit 的方式 |
|---|---|---|---|
| **Matt（内容层）** | 做什么、为什么：打磨想法 → CONTEXT.md 术语 → spec → 拆票 | spec + tickets | `source_artifacts` 按路径引用 |
| **agent-workflow（状态层）** | 谁在哪个阶段、下一步做什么 | `state.yaml` + 阶段机 + CLI | 本仓库即协议源 |
| **Superpowers（质量层）** | 怎么写得好：tdd、调试、验证、评审、worktree | 实现代码 + 测试 | 在实现/评审阶段被调用 |

kit 不取代 Matt/Superpowers，也不要求它们存在——没有它们，kit 一样能跑（`start` 新开票）；有它们时，kit 负责把它们产出的票据装进状态机跟踪。

## 一次性接入

```bash
ai-workflow init --with-skills
```

- 装协议 + 模板到 `.ai/workflow/`，`AGENTS.md` 追加托管块——**你现有的 AGENTS.md / CLAUDE.md / Matt 约定原样保留**（这是 kit 的硬承诺：spec §2.9）。
- `--with-skills` 把 8 个角色技能装进 `.agents/skills/`（自包含模式）；不想复制进仓库的话，技能也可以装到 harness 的全局技能库，仓库只引用角色名——二选一即可，语义相同。

## 两种开票方式

### 已有半成品工作 → `adopt`（迁移路径）

```bash
ai-workflow adopt TICKET-001 --title "..." \
  --spec docs/specs/spec.md --ticket .scratch/feature/01.md --plan docs/plan.md
```

会生成 `.ai/migration-report.md`（自动扫描 git 状态、AGENTS.md、docs、测试目录、最近提交），并在 `.ai/work/TICKET-001/` 搭好带迁移块的状态脚手架。然后由**资深角色**按 `.ai/workflow/MIGRATION.md` 完成：

1. **阶段重建**：把 `historical_phases` 标成 confirmed / inferred / existing / not_performed。
2. **追溯最小证据**：只补"安全继续剩余工作"所需的最小证据，带 Migration Notice，**不是**重走历史。
3. **决策重建**：`decision.md` 带 Provenance，只保留仍然有效的决策。
4. **adoption checkpoint**：六项确认后 `continuation_safe: true`——在这之前，便宜模型（`ticket-executor`）不许接手。

完成后进入正常流转：

```bash
ai-workflow advance TICKET-001 --to evidence_collection
ai-workflow validate
```

### 新功能 → `start`（greenfield 路径）

Matt 流程产出 spec + tickets 之后，直接用：

```bash
ai-workflow start TICKET-002 --title "..." --spec docs/specs/spec.md --ticket .scratch/f/02.md
```

`start` 从模板生成状态，`source_artifacts` 引用 Matt 的产物（不复制）。之后走 [quickstart.md](quickstart.md) 的完整阶段机。

### 直接从实现/评审阶段开票 → 显式 bootstrap 恢复

在 v2 安装上，`start --phase implementation|review` 或 `adopt --phase implementation|review`（资深角色确认工作确实已处于该阶段时）**不会**得到一个看似就绪的半成品状态，而是进入显式的 bootstrap 恢复：

- 请求的 `phase` 保持不变；`source_artifacts` 引用原样保留；绝不伪造 `upgrade` 转换字段。
- 状态文件写入 `recovery.kind: bootstrap`，并记录一条未解决的 `machine` 升级（含 `previous_status` 与被打断的常规下一步），`status` 锁定为 `escalation_required`，路由指向资深角色 `workflow-bootstrap`。
- **初始化的文件 ≠ 就绪的契约**：脚手架里的 `evidence.md`/`handoff.md`/`progress.md` 只是占位，没有审计、没有注册 Plan、没有 `decision.md`。此期间 `advance`/`complete-task`/改状态一律被拒，`resume` 会点名 `workflow-bootstrap` 与未解决的升级。

资深角色用公开命令补齐当前阶段契约后引用式清账：

```bash
# 1. 补证据并审计，绑定门槛（恢复期允许在实现/评审阶段执行 set-gate）
ai-workflow set-gate TICKET --gate sufficient --round 1
# 2. 注册 Plan（恢复期允许在 planning 之外注册；review 阶段需先补记已完成的实现历史）
ai-workflow register-plan TICKET --path docs/plan.md --total 1
# 3. 重建 decision.md；被采纳的仓库还需资深确认六项 adoption_checkpoint
# 4. 带引用的清账（原子检查，拒绝时状态字节不变）
ai-workflow escalate TICKET --clear --resolution "按 evidence.md、decision.md 与 plan.md 重建"
```

清账成功后票回到原阶段：`implementation` 恢复常规执行（`ticket-executor`），`review` 恢复待评审（`reviewer`，verdict 仍为 pending）。清账会把恢复标记解析为已解决（`kind: null`），不再授予任何越阶段权限；此后的普通 `escalate` 按阶段自身的资深路由校验，残留的 `workflow-bootstrap` 路由会被报为路由损坏。**已有的**半成品 v2 状态（没有该标记）不做回填——用普通 `escalate` 进入同一套受检恢复。

## 与 Matt / Superpowers 的具体配合

| kit 阶段 | kit 角色（CLI） | 可叠加的 Matt / Superpowers 技能 |
|---|---|---|
| 证据收集/审计 | repo-scout / evidence-auditor（`advance`/`set-gate`） | Matt `/research`、`/domain-modeling` |
| 技术决策 | technical-decision（`advance --to planning`） | Superpowers `brainstorming`、Matt `/domain-modeling` |
| 计划 | executor-plan（`advance --to implementation`） | Matt `/writing-plans`、Superpowers `writing-plans` |
| 实现 | ticket-executor（`claim`/`complete-task`） | **Superpowers `tdd` / `systematic-debugging` / `verification-before-completion`** |
| 评审 | reviewer（v2：`set-review`）或 checkpoint-handoff（v1：`validate`/`advance`） | Superpowers `requesting/receiving-code-review`、`finishing-a-development-branch` |

## 常见疑问

- **kit 会覆盖我现有的 Matt/Superpowers 配置吗？** 不会。`init` 只在 `AGENTS.md` 追加一个带标记的托管块，块外内容分毫不动；已有 spec/ticket/plan 一律按路径引用。
- **我的仓库已经有 `.scratch/` 票据了，还要重建吗？** 不用。`adopt` 时把它们填进 `source_artifacts`，`historical_phases` 如实标注即可。
- **非要复制技能进仓库吗？** 不是。默认技能装 harness 全局库（零漂移、git pull 即升级）；`--with-skills` 只是给"自包含仓库"的可选路径。
- **已有 v1 Ticket 怎么升到 v2？** 先用 `ai-workflow upgrade` 升级已安装协议（不改任何 Ticket），再用 `upgrade-ticket <ticket-id>` 显式转换单个 active v1 Ticket；随后由资深角色按 [.ai/workflow/MIGRATION.md](../.ai/workflow/MIGRATION.md) 重建当前阶段契约并 `escalate --clear --resolution`。转换保留阶段/引用/已完成计数，重置 gate/review，绝不伪造历史审计、Plan 或 review；历史已 `done` 的 Ticket 保持 v1。
- **`adopt` 产出 v1 还是 v2？** 当前安装默认 `workflow_version: 2`，故 `adopt` 产出 v2 脚手架且六个 checkpoint 布尔全为 `false`；未升级的 v1 安装仍产出 v1。adoption 语义（历史标注、追溯最小证据、检查点门禁）两版一致。
- **`adopt` 和 `start` 什么区别？** `adopt` = 已有仓库/半成品（迁移语义，带历史标注与检查点）；`start` = 全新工作（greenfield，从模板干净起票）。
- **直接从实现/评审阶段开票为什么被锁住？** 这是设计而非故障：该阶段还没有证据、Plan 和 decision，脚手架不允许表现得"可执行"。`start/adopt --phase implementation|review` 会进入显式 bootstrap 恢复（`recovery.kind: bootstrap` + 未解决升级，路由 `workflow-bootstrap`），由资深角色按上方"公开恢复序列"补齐契约后 `escalate --clear --resolution` 清账；初始化的脚手架文件本身不是就绪契约。
