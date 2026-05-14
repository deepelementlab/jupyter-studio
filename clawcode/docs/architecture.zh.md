# 架构设计

ClawCode 是一款基于模块化分层架构构建的终端原生 AI 编程助手。

## 产品视角
<p align="center">
<img width="676" height="368" alt="Generated_image" src="https://github.com/user-attachments/assets/45741c3e-b8b4-45df-86a3-00dec3b86f8a" />
</p>

## 系统概览

```
┌──────────────────────────────────────────────────────────┐
│                      TUI 层                               │
│  ┌──────────────────────────────────────────────────┐    │
│  │  ClawCodeApp (Textual)                            │    │
│  │  ┌────────────┬──────────────┬────────────────┐  │    │
│  │  │ 聊天界面   │ 侧边栏       │ HUD/状态栏     │  │    │
│  │  └────────────┴──────────────┴────────────────┘  │    │
│  └──────────────────────────────────────────────────┘    │
│                           │                               │
├───────────────────────────┼───────────────────────────────┤
│                      CLI 层                               │
│  ┌──────────────────────────────────────────────────┐    │
│  │  基于 Click 的 CLI (clawcode.cli.commands)       │    │
│  │  - 交互模式      - 非交互模式 (-p)                │    │
│  │  - 斜杠命令      - 插件子命令                     │    │
│  └──────────────────────────────────────────────────┘    │
│                           │                               │
├───────────────────────────┼───────────────────────────────┤
│                    应用层                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ AppContext   │  │ SessionSvc   │  │ MessageSvc    │  │
│  │ PluginMgr    │  │ LSPManager   │  │ HistoryComp   │  │
│  └──────────────┴──┴──────────────┴──┴───────────────┘  │
│                           │                               │
├───────────────────────────┼───────────────────────────────┤
│                    核心引擎                               │
│  ┌──────────────────────────────────────────────────┐    │
│  │  CoderRuntimeBundle (运行时组装工厂)              │    │
│  │  ┌──────────────┐  ┌──────────────────────────┐  │    │
│  │  │ 提供商       │  │ 工具注册表               │  │    │
│  │  │ Anthropic    │  │ file_ops, bash, search   │  │    │
│  │  │ OpenAI       │  │ subagent, advanced       │  │    │
│  │  │ Gemini       │  │ browser, desktop, mcp    │  │    │
│  │  │ 200+ 模型    │  │ 44 个内置工具            │  │    │
│  │  └──────────────┘  └──────────────────────────┘  │    │
│  └──────────────────────────────────────────────────┘    │
│                           │                               │
├───────────────────────────┼───────────────────────────────┤
│                    代理层                                 │
│  ┌─────────────────────┐  ┌──────────────────────────┐  │
│  │ Agent (普通代理)    │  │ ClawAgent (Claw 模式)    │  │
│  │ - ReAct 循环       │  │ - 多步骤工作              │  │
│  │ - 子代理生成       │  │ - 迭代预算                │  │
│  │ - 工具编排         │  │ - 子代理协调              │  │
│  │ - 计划/执行        │  │ - 深度收敛                │  │
│  └─────────────────────┘  └──────────────────────────┘  │
│                           │                               │
├───────────────────────────┼───────────────────────────────┤
│                    学习层                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ LearningSvc  │  │ ECAP 引擎    │  │ TECAP 引擎    │  │
│  │ 质量门禁     │  │ 经验         │  │ 团队经验      │  │
│  │ DeepLoop     │  │ 本能         │  │ 协调          │  │
│  └──────────────┘  └──────────────┘  └───────────────┘  │
│                           │                               │
├───────────────────────────┼───────────────────────────────┤
│                    存储层                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ SQLite       │  │ JSON 文件    │  │ Markdown      │  │
│  │ 会话         │  │ 设置         │  │ 代理角色      │  │
│  │ 消息         │  │ 经验         │  │ 技能          │  │
│  └──────────────┘  └──────────────┘  └───────────────┘  │
└──────────────────────────────────────────────────────────┘
```

## 核心组件

### 1. 运行时捆绑工厂

`CoderRuntimeBundle` 组装代理运行所需的所有组件：

```python
bundle = build_coder_runtime(
    settings=settings,
    session_service=session_svc,
    message_service=message_svc,
    permissions=permissions,
    plugin_manager=plugin_mgr,
    style="cli_non_interactive",
)
agent = bundle.make_plain_agent()
```

### 2. 提供商抽象

`BaseProvider` 支持多个 LLM 后端：

| 提供商 | SDK | 模型 |
|--------|-----|------|
| Anthropic | `anthropic` | Claude 3.5/4, Sonnet, Opus |
| OpenAI | `openai` | GPT-4, o系列, Codex |
| Gemini | `google-generativeai` | Gemini 1.5/2.0 |
| OpenAI兼容 | `openai` | DeepSeek, GLM, Qwen, Kimi, Ollama... |

### 3. 代理事件协议

代理执行产生类型化事件：

```python
AgentEventType.THINKING       # LLM 推理令牌
AgentEventType.CONTENT_DELTA  # 流式文本
AgentEventType.TOOL_USE       # 工具调用开始
AgentEventType.TOOL_RESULT    # 工具执行结果
AgentEventType.USAGE          # Token 用量统计
AgentEventType.RESPONSE       # 完整响应
AgentEventType.ERROR          # 错误
```

### 4. 工具架构

44 个内置工具按类别组织：

| 类别 | 工具 | 描述 |
|------|------|------|
| 文件 I/O | `view`, `ls`, `write`, `edit`, `patch`, `glob`, `grep`, `fetch` | 工作区文件操作 |
| Shell | `bash`, `terminal`, `process`, `execute_code` | 命令执行 |
| 搜索 | `diagnostics`, `web_search`, `web_extract`, `session_search` | 代码/Web 诊断 |
| 浏览器 | `browser_*` (×11) | 浏览器自动化 |
| 代理 | `Agent` | 子代理生成 |
| 任务 | `TodoWrite`, `TodoRead`, `UpdateProjectState` | 状态管理 |
| 集成 | `mcp_call`, `sourcegraph`, `desktop_*` | 外部服务 |

### 5. 配置系统

多源配置，优先级如下：

1. 默认值（Pydantic 模型）
2. JSON 配置文件（`.clawcode.json`）
3. 环境变量（`CLAWCODE_*`）
4. `.env` 文件

## 执行流程

```
用户输入 → CLI/TUI → AppContext → 创建会话 → CoderRuntimeBundle
                                                                    ↓
                                                              Agent.run()
                                                                    ↓
                                                      ┌─ ReAct 循环 ─┐
                                                      │ LLM → 工具   │
                                                      │ → 执行       │
                                                      │ → 观察       │
                                                      └──────────────┘
                                                                    ↓
                                                       消息/事件流
                                                                    ↓
                                              TUI 显示 / CLI 输出
```

## 目录结构

```
clawcode/
├── clawcode/
│   ├── cli/                  # Click CLI 定义
│   ├── tui/                  # Textual TUI 应用
│   │   ├── screens/          # 聊天、帮助、日志界面
│   │   ├── components/       # 输入、消息列表、对话框
│   │   ├── builtin_slash.py  # 斜杠命令注册表
│   │   └── hud/              # 抬头显示
│   ├── llm/                  # 核心 LLM 集成
│   │   ├── agent.py          # ReAct 代理循环
│   │   ├── claw.py           # ClawAgent 模式
│   │   ├── providers/        # LLM 提供商实现
│   │   ├── tools/            # 内置工具
│   │   └── runtime_bundle.py # 组装工厂
│   ├── learning/             # ECAP/TECAP 学习
│   ├── config/               # 设置和常量
│   ├── session/              # 会话管理
│   └── plugin/               # 插件系统
├── .claw/                    # 项目配置（代理、设计）
└── docs/                     # 文档
```

## 相关文档

| 主题 | 链接 |
|------|------|
| 项目概述 | [README.zh.md](../README.zh.md) |
| 代理与团队编排 | [agent-team-orchestration.zh.md](./agent-team-orchestration.zh.md) |
| ECAP/TECAP 学习 | [ecap-learning.zh.md](./ecap-learning.zh.md) |
| 斜杠命令参考 | [slash-commands.zh.md](./slash-commands.zh.md) |
| 配置指南 | [clawcode-configuration.md](./clawcode-configuration.md) |
