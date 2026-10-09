# agent-workflow

仓库原生的、跨 Harness 的 Agent 工作流协议 + CLI + 角色技能。

> 一句话：**任何能读写 Git 仓库的编码 Agent（Codex / TRAE / ZCode…），进仓库看一眼 `state.yaml` 就知道"做什么任务 → 在哪个阶段 → 有什么证据 → 下一步谁做"**，不依赖聊天历史。仓库本身就是工作流状态的事实源。

## 核心思想

- **仓库即事实源**：`state.yaml` 是每个 ticket 的权威状态（第一个要读的文件），Chat 历史永远不算数。
- **阶段机**：`requirement → evidence_collection → evidence_audit → technical_decision → planning → implementation → review → done`（evidence 不足时走 `followup_evidence` 循环）。
- **角色**：scout / evidence-auditor / technical-decision / executor-plan / ticket-executor / reviewer / checkpoint-handoff（外加处理遗留迁移的 workflow-bootstrap），每个阶段有对应的角色和模型档位。
- **工作流版本**：新工作默认 `workflow_version: 2`（结构化 artifact 契约、字节身份门禁、review 结论、已注册 Plan）；已有 v1 Ticket 与未升级的 v1 安装保持 v1 语义不变，需要时用 `upgrade-ticket` 显式转换。
- **状态推进走 CLI**：`advance` / `set-gate` / `complete-task` 等语义命令在**写入时**就校验合法性与证据门禁，不用手写受限 YAML。

## 三层协作（与 Matt / Superpowers 搭配）

| 层 | 管什么 | 代表技能 |
|---|---|---|
| **Matt（内容层）** | 做什么、为什么：打磨想法 → CONTEXT.md 术语 → spec → 拆票 | `/grill-with-docs`、`/to-spec`、`/to-tickets` |
| **agent-workflow（状态层）** | 谁在哪个阶段、下一步做什么 | 本仓库 CLI + 角色技能 |
| **Superpowers（质量层）** | 怎么写得好 | `tdd`、`systematic-debugging`、`verification-before-completion`、`code-review` |

kit 不取代它们：Matt 出方案和票，kit 管状态流转，Superpowers 保实现质量。接口就是 `.scratch/` 票据 + `state.yaml` + CLI。详见 [docs/users/adopting-existing.md](docs/users/adopting-existing.md)。

## 获取本 kit

本 kit 不是 pip 包——零依赖（[ADR-0002](docs/adr/0002-restricted-yaml-subset-parser-over-pyyaml.md)）+ 协议 repo-native（[ADR-0001](docs/adr/0001-repo-native-protocol-over-harness-skills.md)）决定它只能 clone 使用。CLI 从 kit 仓库自身读协议源（`_kit_root()` 按 `__file__` 定位），所以 **kit 仓库必须本地存在**，`pip install` 到 site-packages 会找不到协议。

```bash
# clone（或作为 submodule 接进已有仓库）
git clone https://github.com/kevinke/agent-workflow.git
cd agent-workflow

# 可选：让 ai-workflow 成为命令名，免去每次写 python .../main.py
alias ai-workflow="python $(pwd)/scripts/ai-workflow/main.py"
```

之后在**目标仓库**里调用（`target` 参数默认是 `cwd`）：

```bash
cd <目标仓库>
python /path/to/agent-workflow/scripts/ai-workflow/main.py init --with-skills
# 装好后，alias 生效即可直接用 ai-workflow status / validate / advance ...
```

> **dogfood 隔离**：`init --with-skills` 把协议+模板+技能全装进目标仓库，不依赖也不写 harness 全局 skill 库，删仓库即清理干净，不影响其他仓库。两种技能放置方式的取舍见 [docs/users/adopting-existing.md](docs/users/adopting-existing.md)。

## 快速上手（绿色字段新仓库）

```bash
# 1. 安装协议（可选 --with-skills 顺带装 8 个角色技能）
ai-workflow init
ai-workflow install-skills          # 或 init --with-skills

# 2. 开一个 ticket
ai-workflow start TICKET-001 --title "..."

# 3. 走阶段机（每个阶段写对应 artifact，validate 在阶段边界把关；新票默认 v2）
ai-workflow advance TICKET-001 --to evidence_collection   # 写 evidence.md
ai-workflow advance TICKET-001 --to evidence_audit        # 写 evidence-audit.md
ai-workflow set-gate TICKET-001 --gate sufficient --round 1
ai-workflow advance TICKET-001 --to technical_decision    # 写 decision.md
ai-workflow advance TICKET-001 --to planning              # 写 plan
ai-workflow register-plan TICKET-001 --path progress.md --total 3  # v2：注册 Plan（实现前必需）
ai-workflow advance TICKET-001 --to implementation
ai-workflow complete-task TICKET-001                      # 每完成一个任务跑一次
ai-workflow advance TICKET-001 --to review
ai-workflow set-review TICKET-001 --verdict pass          # v2：记录 Reviewer 结论（done 前必需）
ai-workflow advance TICKET-001 --to done

# 4. 随时看状态 / 校验
ai-workflow status TICKET-001
ai-workflow validate
```

完整的分步讲解见 [docs/users/quickstart.md](docs/users/quickstart.md)。

## 在已有仓库用（adopt 迁移路径）

```bash
ai-workflow init --with-skills
ai-workflow adopt TICKET-001 --title "..." --spec docs/spec.md --ticket .scratch/f/01.md
# 资深角色按 MIGRATION.md 补证据/决策/检查点 → ai-workflow advance 进入正常流转
```

已有 Matt/Superpowers 痕迹的仓库（有 AGENTS.md、CONTEXT.md、.scratch/ 票据等）走 `adopt`：现有 spec/ticket/plan 按路径引用进 `source_artifacts`（不复制），历史阶段按 confirmed/inferred 标注，绝不伪造历史。详见 [docs/users/adopting-existing.md](docs/users/adopting-existing.md)。

## 升级到 v2（已有 v1 仓库）

`workflow_version: 2` 是当前默认发布：新 `init`/`start` 直接产出 v2，已有 v1 Ticket 与未升级的 v1 安装保持 v1 语义不变。把协议和某个 Ticket 显式升到 v2：

```bash
ai-workflow upgrade                        # 升级已安装协议（不改任何 Ticket 的 state.yaml）
ai-workflow upgrade-ticket TICKET-001      # 把该 active v1 Ticket 转为 v2（记录 upgrade 块）
# 资深角色按 MIGRATION.md 重建当前阶段契约：set-gate / register-plan / 补齐 artifact，
ai-workflow escalate TICKET-001 --clear --resolution "当前阶段契约已重建"
```

`upgrade-ticket` 绝不伪造历史审计、Plan 或 review pass：它保留阶段、引用与已完成计数，重置 gate/review，并生成一个由 `workflow-bootstrap` 解决的重建升级；历史已 `done` 的 Ticket 保持 v1。详见 [.ai/workflow/MIGRATION.md](.ai/workflow/MIGRATION.md)。

## 命令总览

| 命令 | 作用 |
|---|---|
| `init [target] [--with-skills]` | 安装协议 + 模板 + AGENTS.md 托管块（幂等，不覆盖现有内容） |
| `install-skills [target]` | 把 8 个角色技能装进目标仓库（幂等更新） |
| `status [ticket]` | 一屏状态：ticket / phase / status / task N/M / gate / next |
| `validate [ticket]` | 校验工作流本身：ERROR 必改，WARN 记录即可；非零退出表示有 ERROR |
| `start <ticket> [opts]` | 新开 greenfield ticket（从模板生成，含 source_artifacts 指针） |
| `adopt <ticket> [opts]` | 已有/遗留仓库迁移：迁移报告 + 状态脚手架 |
| `advance <ticket> --to <phase>` | 沿状态机推进（写入时校验转移合法性与证据门禁） |
| `claim <ticket> [--harness H] [--model M]` | 标记本会话在工作 |
| `release <ticket>` | 清空 claim（保留 provenance） |
| `complete-task <ticket> [--total N]` | 实现阶段完成任务计数 |
| `register-plan <ticket> --path P --total N` | 注册引用的执行 Plan（v2，绑定 Plan 字节哈希与各任务哈希） |
| `set-gate <ticket> --gate G [--round N]` | 记录证据审计结论 |
| `prepare-review <ticket> --commit <literal-oid> --output <new-dir>` | 为隔离 review 准备可丢弃快照：独立 clone（Git 元数据与 live 分离）+ 注册 Plan/校验输入的原始字节副本 + 监督者清单 `meta/context.json`（分别固定 live 与 snapshot 身份）；失败不留半成品，也不碰 live 文件 |
| `run-review <ticket> --review-context <dir> --kind baseline\|probe -- <argv…>` | 在受强制的 `linux-bwrap-v1` 边界内运行验证命令并写监督者回执（捕获 stdout/stderr、记录命令自身退出码与 snapshot 残留改动）。`baseline` 是验收入口运行、`probe` 是声明式 snapshot 内改动；边界阻塞器退出 1，绝不回退为无约束运行 |
| `set-review <ticket> --verdict V [--review-context <dir> --report <candidate-review.md> --handoff <candidate-handoff.md>]` | 记录 Reviewer 结论（v2：pass / changes_requested）。带保留 `## Isolation provenance` 段的隔离报告只能经这三个守卫选项发布：发布前重新核对 live 基线，只写本 Ticket 的 Review/State/Handoff，不给出结论也不做阶段转移；一旦发布即消耗该 context（每个结论需重新 prepare）。无守卫形式的普通用法保持历史 binding 行为 |
| `escalate <ticket> --scope S --reason "..." \| --clear` | 设置/清除升级 |
| `set-status <ticket> --status S` | 设置横向状态（blocked/paused/abandoned…） |
| `resume <ticket>` | 只读续接简报（有 ERROR 阻断时退出 1） |
| `upgrade` | 显式协议升级（workflow_version，不改 Ticket） |
| `upgrade-ticket <ticket>` | 把单个 active v1 Ticket 显式转换为 v2（记录资深重建） |

## 文档地图

结构化交接（Decision Scout、执行契约、review 门禁、跨 Harness 接手）已实现并随
`workflow_version: 2` 默认发布：新开票即 v2，已有 Ticket 保持 v1，需要时用
`upgrade-ticket` 显式转换并重建当前阶段契约。背景见
[Decision Scout 与结构化交接 spec](.scratch/decision-scout-port/spec.md)
和 [实施票据](.scratch/decision-scout-port/tickets.md)。

- **本套件是什么 / 怎么设计**：[docs/specs/agent-workflow-protocol.md](docs/specs/agent-workflow-protocol.md)
- **安装到目标仓库的协议正文**：`.ai/workflow/`（PROTOCOL / STATE_SCHEMA / ARTIFACTS / ROLES / ESCALATION / MIGRATION）
- **Windows 上的 Codex 启动诊断**：[adapters/codex/windows.md](adapters/codex/windows.md)（策略拒绝 ≠ 模型结论；只读诊断与停止条件；这些观察**不构成**任何写限制证明，因此 Windows 与 Codex Desktop/MCP 会话的隔离 review 仍不支持）
- **本地隔离 review 边界**：[adapters/local-review.md](adapters/local-review.md)（`linux-bwrap-v1` 实测挂载表、EROFS/EXDEV/ENETUNREACH 拒绝证据与诚实限制）
- **决策记录**：[docs/adr/](docs/adr/)（仓库原生协议、受限 YAML、纯 stdlib CLI）
- **领域术语**：[CONTEXT.md](CONTEXT.md)
- **开发约定**：[docs/agents/](docs/agents/)（domain / issue-tracker）
- **票据**：`.scratch/<feature>/issues/`
- **测试**：`scripts/ai-workflow/tests/`（482 个用例，含端到端 dogfood、完整安装生命周期与隔离 review 安装生命周期）
