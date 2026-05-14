# 代理与团队编排

ClawCode 提供丰富的多代理系统，从简单子代理到完整的研发团队编排。

## 子代理系统

主代理可以生成具有隔离上下文、自定义提示词和工具白名单的**子代理**。

### 内置子代理角色

| 代理 ID | 用途 | 工具访问 |
|---------|------|----------|
| `explore` | 只读探索 | `Read`, `Glob`, `Grep`, ... |
| `plan` | 规划研究 | 只读工具 |
| `code-review` | 代码评审 | 只读工具 |
| `general-purpose` | 全功能 | 所有（不含委托工具） |

### 调用子代理

```json
{
  "agent": "plan",
  "task": "梳理认证是如何实现的；列出关键文件。"
}
```

别名：`subagent_type` ↔ `agent`，`prompt` ↔ `task`。

## ClawTeam：多角色编排

`/clawteam` 在一条命令中编排包含 14+ 专业角色的虚拟研发团队。

### 角色注册表

| 角色 ID | 职责 |
|---------|------|
| `product-manager` | 优先级、路线图、验收标准 |
| `business-analyst` | 流程、规则、边界情况 |
| `system-architect` | 架构、技术选型、非功能需求 |
| `ui-ux-designer` | 信息架构、UX 约束 |
| `dev-manager` | 节奏、风险、里程碑 |
| `team-lead` | 技术决策、质量基线 |
| `rnd-backend` | 服务、API、数据层 |
| `rnd-frontend` | UI 组件、状态、集成 |
| `rnd-mobile` | 移动端/跨平台开发 |
| `devops` | CI/CD、流水线、环境 |
| `qa` | 测试策略、门禁、回归 |
| `sre` | 可用性、SLO、运维手册 |
| `project-manager` | 范围、进度、变更控制 |
| `scrum-master` | 迭代节奏、障碍排除 |

### 使用方式

```bash
/clawteam <你的需求>
/clawteam:<角色> <特定任务>
/clawteam --deep_loop <复杂任务>
```

### 深度循环：收敛式迭代

`/clawteam --deep_loop` 运行多轮收敛迭代：

1. 每轮结构化契约（目标、交接、差距）
2. 解析 `DEEP_LOOP_WRITEBACK_JSON` 实现自动写回
3. 可调的收敛阈值、最大迭代次数
4. 跨轮次一致性检查

收敛设置（`.clawcode.json`）：
```json
{
  "closed_loop": {
    "clawteam_deeploop_enabled": true,
    "clawteam_deeploop_max_iters": 100,
    "clawteam_deeploop_convergence_rounds": 2,
    "clawteam_deeploop_handoff_target": 0.85
  }
}
```

## 自定义代理角色

使用带 YAML 前元的 Markdown 文件定义自定义角色：

```markdown
---
name: api-guardian
description: 仅审查公共 HTTP API 变更。
tools:
  - Read
  - Glob
  - Grep
  - diagnostics
maxTurns: 24
---

你只分析 API 路由和 OpenAPI/契约文件。
将破坏性变更以列表形式报告。
```

### 发现路径

| 范围 | 路径 |
|------|------|
| 用户级 | `~/.claude/agents/*.md` |
| 项目级 | `.claw/agents/*.md`, `.clawcode/agents/*.md`, `.claude/agents/*.md` |

## 计划模式

在计划模式（`/plan`）下，仅允许以下子代理：
- `plan`
- `explore`
- `code-review`

所有工具被限制为**只读**策略。

## 多模型工作流

| 命令 | 聚焦 |
|------|------|
| `/multi-plan` | 协作规划（仅限计划类代理） |
| `/multi-execute` | 协作执行，可追溯产物 |
| `/multi-backend` | 后端聚焦工作流 |
| `/multi-frontend` | 前端聚焦工作流 |
| `/multi-workflow` | 全栈工作流（后端 + 前端） |

## 相关文档

| 主题 | 链接 |
|------|------|
| 架构设计 | [architecture.zh.md](./architecture.zh.md) |
| ECAP/TECAP 学习 | [ecap-learning.zh.md](./ecap-learning.zh.md) |
| 斜杠命令参考 | [slash-commands.zh.md](./slash-commands.zh.md) |
