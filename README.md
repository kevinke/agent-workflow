# agent-workflow

仓库原生的、跨 Harness 的 Agent 工作流协议 + CLI + 角色技能。

> 一句话：**任何能读写 Git 仓库的编码 Agent（Codex / TRAE / ZCode…），进仓库看一眼 `state.yaml` 就知道"做什么任务 → 在哪个阶段 → 有什么证据 → 下一步谁做"**，不依赖聊天历史。仓库本身就是工作流状态的事实源。

## 核心思想

- **仓库即事实源**：`state.yaml` 是每个 ticket 的权威状态（第一个要读的文件），Chat 历史永远不算数。
- **阶段机**：`requirement → evidence_collection → evidence_audit → technical_decision → planning → implementation → review → done`（evidence 不足时走 `followup_evidence` 循环）。
- **角色**：scout / evidence-auditor / technical-decision / executor-plan / ticket-executor / checkpoint-handoff，每个阶段有对应的角色和模型档位。
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
# 1. 安装协议（可选 --with-skills 顺带装 7 个角色技能）
ai-workflow init
ai-workflow install-skills          # 或 init --with-skills

# 2. 开一个 ticket
ai-workflow start TICKET-001 --title "..."

# 3. 走阶段机（每个阶段写对应 artifact，validate 在阶段边界把关）
ai-workflow advance TICKET-001 --to evidence_collection   # 写 evidence.md
ai-workflow advance TICKET-001 --to evidence_audit        # 写 evidence-audit.md
ai-workflow set-gate TICKET-001 --gate sufficient --round 1
ai-workflow advance TICKET-001 --to technical_decision    # 写 decision.md
ai-workflow advance TICKET-001 --to planning              # 写 plan
ai-workflow advance TICKET-001 --to implementation
ai-workflow complete-task TICKET-001 --total 3            # 每完成一个任务跑一次
ai-workflow advance TICKET-001 --to review
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

## 命令总览

| 命令 | 作用 |
|---|---|
| `init [target] [--with-skills]` | 安装协议 + 模板 + AGENTS.md 托管块（幂等，不覆盖现有内容） |
| `install-skills [target]` | 把 7 个角色技能装进目标仓库（幂等更新） |
| `status [ticket]` | 一屏状态：ticket / phase / status / task N/M / gate / next |
| `validate [ticket]` | 校验工作流本身：ERROR 必改，WARN 记录即可；非零退出表示有 ERROR |
| `start <ticket> [opts]` | 新开 greenfield ticket（从模板生成，含 source_artifacts 指针） |
| `adopt <ticket> [opts]` | 已有/遗留仓库迁移：迁移报告 + 状态脚手架 |
| `advance <ticket> --to <phase>` | 沿状态机推进（写入时校验转移合法性与证据门禁） |
| `claim <ticket> [--harness H] [--model M]` | 标记本会话在工作 |
| `release <ticket>` | 清空 claim（保留 provenance） |
| `complete-task <ticket> [--total N]` | 实现阶段完成任务计数 |
| `set-gate <ticket> --gate G [--round N]` | 记录证据审计结论 |
| `escalate <ticket> --scope S --reason "..." \| --clear` | 设置/清除升级 |
| `set-status <ticket> --status S` | 设置横向状态（blocked/paused/abandoned…） |
| `upgrade` | 显式协议升级（workflow_version） |

## 文档地图

- **本套件是什么 / 怎么设计**：[docs/specs/agent-workflow-protocol.md](docs/specs/agent-workflow-protocol.md)
- **安装到目标仓库的协议正文**：`.ai/workflow/`（PROTOCOL / STATE_SCHEMA / ARTIFACTS / ROLES / ESCALATION / MIGRATION）
- **决策记录**：[docs/adr/](docs/adr/)（仓库原生协议、受限 YAML、纯 stdlib CLI）
- **领域术语**：[CONTEXT.md](CONTEXT.md)
- **开发约定**：[docs/agents/](docs/agents/)（domain / issue-tracker）
- **票据**：`.scratch/<feature>/issues/`
- **测试**：`scripts/ai-workflow/tests/`（104 个用例，含端到端 dogfood）
