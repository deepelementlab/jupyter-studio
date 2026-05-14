# ECAP 与 TECAP 学习系统

ClawCode 内置独特的基于经验的学习框架，将开发数据转化为可复用、可进化的知识。

<p align="center">
<img width="800" height="400" alt="ECAP技术示例" src="https://github.com/user-attachments/assets/099277b5-4d02-4669-9cc0-260efc8bc79b" />
</p>

## 概览

```
想法 → 记忆 → 规划 → 编码 → 验证 → 评审 → 学到的经验
```

## 核心概念

### 经验
表示目标与结果之间差距的函数。差距驱动改进。

**维度**：model_experience, agent_experience, skill_experience, team_experience

### ECAP（经验胶囊）
个人/任务级胶囊，表示可进化的三元组：
```
（本能, 经验, 技能）
```

### TECAP（团队经验胶囊）
团队协作胶囊，包含：
- 协作步骤与拓扑
- 角色间交接
- 每个团队成员的角色级 ECAP 三元组

## 学习流程

```
任务执行与工具观察
       ↓
经验信号提取
       ↓
ECAP 创建与结构化存储
       ↓
ECAP 检索与应用于新工作
       ↓
结果与验证
       ↓
经验反馈评分
       ↓
本能_经验_技能进化
       ↓
clawteam 协作
       ↓
TECAP 创建或升级
       ↓
团队经验应用上下文
       ↓
深度循环收敛与写回
       ↓
（循环回经验信号提取）
```

## 实现

### 经验信号提取

```bash
/learn                    # 从最近的工具观察中学习
/learn-orchestrate        # 观察 → 进化 → 导入技能存储
```

### ECAP 生命周期

| 命令 | 用途 |
|------|------|
| `/experience-create` | 从最近的观察创建 ECAP |
| `/experience-status` | 列出可用胶囊（带筛选） |
| `/experience-export` | 导出为 JSON/Markdown |
| `/experience-import` | 从文件或 URL 导入 |
| `/experience-apply` | 作为一次性提示上下文应用 |
| `/experience-feedback` | 记录成功/失败评分 |

### TECAP 生命周期

| 命令 | 用途 |
|------|------|
| `/team-experience-create` | 从协作痕迹创建 |
| `/team-experience-status` | 按团队/问题筛选列出 |
| `/team-experience-export` | 导出为 JSON/Markdown |
| `/team-experience-import` | 从文件或 URL 导入 |
| `/team-experience-apply` | 作为协作上下文应用 |
| `/team-experience-feedback` | 记录反馈评分 |

短别名：`/tecap-*`（映射到 `/team-experience-*`）

### 存储结构

```
<数据目录>/
├── learning/
│   ├── experience/
│   │   ├── capsules/     # ECAP 胶囊
│   │   └── exports/      # 导出的胶囊
│   ├── team_experience/  # TECAP 胶囊
│   ├── observations/     # 原始观察
│   └── feedback.jsonl    # 反馈评分
└── ...
```

### 治理与隐私

- **隐私级别**：脱敏、审计跟踪、反馈评分
- **兼容标志**：`--v1-compatible` 用于迁移
- **质量门禁**：胶囊应用前验证
- **治理元数据**：`schema_meta`, `quality_score`, `transfer`

## 学习路径

```
模型 → 代理 → 团队
本能 → 经验 → 技能
```

1. **本能**：从观察中提取的低级可复用规则
2. **经验**：带有上下文和结果的结构化胶囊
3. **技能**：进化后的技能，可用于未来任务

## 仪表盘与可观测性

```bash
/experience-dashboard              # ECAP 指标仪表盘
/experience-dashboard --json       # JSON 输出
/experience-dashboard --no-alerts  # 无告警噪音
/closed-loop-contract              # 配置契约覆盖率
/instinct-status                   # 按领域查看已学本能
/instinct-export                   # 带筛选导出本能
```

## 相关文档

| 主题 | 链接 |
|------|------|
| 架构设计 | [architecture.zh.md](./architecture.zh.md) |
| 代理与团队编排 | [agent-team-orchestration.zh.md](./agent-team-orchestration.zh.md) |
| 斜杠命令参考 | [slash-commands.zh.md](./slash-commands.zh.md) |
