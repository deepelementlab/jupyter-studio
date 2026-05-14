# 斜杠命令参考

ClawCode 中所有内置斜杠命令的完整参考。

## 架构与评审

| 命令 | 功能 |
|------|------|
| `/architect` | 架构设计与评审，含权衡分析和 ADR |
| `/code-review` | 审查本地未提交变更，按严重性排序 |
| `/security-review` | 对当前分支待提交变更进行安全审查 |
| `/review` | 审查拉取请求 |

## 规划

| 命令 | 功能 |
|------|------|
| `/plan` | 启用计划模式或查看当前会话计划 |
| `/arc-plan` | 生成一次性替代实现计划（ARC 规划器） |

## 测试驱动开发

| 命令 | 功能 |
|------|------|
| `/tdd` | 严格 TDD 工作流：脚手架 → RED → GREEN → 重构 → 覆盖率门禁 |

## 多角色编排

| 命令 | 功能 |
|------|------|
| `/clawteam` | 多角色任务编排，通过 `/clawteam:<代理>` 指定单一角色 |
| `/clawteam --deep_loop` | 迭代收敛与写回 |
| `/clawteam-deeploop-finalize` | 解析 DEEP_LOOP_WRITEBACK_JSON 并终结 |
| `/multi-plan` | 多模型协作规划 |
| `/multi-execute` | 多模型协作执行，可追溯产物 |
| `/multi-backend` | 后端聚焦多模型工作流 |
| `/multi-frontend` | 前端聚焦多模型工作流 |
| `/multi-workflow` | 全栈多模型工作流 |
| `/orchestrate` | 顺序多角色工作流，含交接 |
| `/orchestrate show\|list` | 显示/列出编排角色 |

## 学习循环（ECAP/TECAP）

| 命令 | 功能 |
|------|------|
| `/learn` | 从最近的工具观察中学习可复用的本能 |
| `/learn-orchestrate` | 观察 → 进化 → 导入技能存储 |
| `/experience-create` | 从最近的观察/本能创建 ECAP |
| `/experience-status` | 列出可用 ECAP 胶囊 |
| `/experience-export` | 将 ECAP 导出为 JSON/Markdown |
| `/experience-import` | 从文件或 URL 导入 ECAP |
| `/experience-apply` | 将 ECAP 作为一次性上下文应用 |
| `/experience-feedback` | 记录反馈评分 |
| `/team-experience-create` | 从协作痕迹创建 TECAP |
| `/team-experience-status` | 列出 TECAP 胶囊 |
| `/team-experience-export` | 将 TECAP 导出为 JSON/Markdown |
| `/team-experience-import` | 从文件或 URL 导入 TECAP |
| `/team-experience-apply` | 将 TECAP 作为协作上下文应用 |
| `/team-experience-feedback` | 记录 TECAP 反馈评分 |
| `/tecap-*` | `/team-experience-*` 的短别名 |
| `/instinct-status` | 按领域/置信度显示已学本能 |
| `/instinct-import` | 从文件或 URL 导入本能 |
| `/instinct-export` | 带筛选导出本能 |
| `/evolve` | 聚类本能，生成进化结构 |
| `/experience-dashboard` | ECAP 指标仪表盘（加 `--json` 或 `--no-alerts`） |
| `/closed-loop-contract` | 显示配置契约覆盖率 |

## 可观测性与诊断

| 命令 | 功能 |
|------|------|
| `/doctor` | 诊断安装和设置 |
| `/diff` | 查看未提交变更和每轮差异 |
| `/debug` | 通过日志调试当前会话 |
| `/insights` | 生成分析报告 |

## 会话与 Git

| 命令 | 功能 |
|------|------|
| `/checkpoint` | Git 工作流检查点：创建、验证、列出、清除 |
| `/rewind` | 软归档聊天，检查/恢复受跟踪的 Git 文件 |
| `/tasks` | 列出和管理后台任务 |
| `/init` | 在项目初始化 CLAWCODE.md |
| `/add-dir` | 添加新的工作目录 |

## 代理、技能与 MCP

| 命令 | 功能 |
|------|------|
| `/agents` | 管理代理配置 |
| `/skills` | 列出可用技能 |
| `/mcp` | 管理 MCP 服务器 |
| `/hooks` | 管理工具事件的钩子配置 |
| `/permissions` | 管理允许/拒绝工具权限规则 |
| `/memory` | 编辑爪记忆文件 |
| `/pr-comments` | 获取 GitHub 拉取请求的评论 |

## Claw 模式与外部 CLI

| 命令 | 功能 |
|------|------|
| `/claw` | 启用 Claw 代理模式或显示状态 |
| `/claude` | Claw 模式 + Anthropic + Claude Code HTTP 身份 |
| `/claude-cli` | Claw 模式 + 在工作区运行 claude/claude-code CLI |
| `/opencode-cli` | Claw 模式 + 在工作区运行 OpenCode CLI |
| `/codex-cli` | Claw 模式 + 在工作区运行 OpenAI Codex CLI |

## 插件

| 命令 | 功能 |
|------|------|
| `/plugin` | 管理 clawcode 插件 |

## 相关文档

| 主题 | 链接 |
|------|------|
| 架构设计 | [architecture.zh.md](./architecture.zh.md) |
| 代理与团队编排 | [agent-team-orchestration.zh.md](./agent-team-orchestration.zh.md) |
| ECAP/TECAP 学习 | [ecap-learning.zh.md](./ecap-learning.zh.md) |
