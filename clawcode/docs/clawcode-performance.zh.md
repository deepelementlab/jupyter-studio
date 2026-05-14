# 性能与测试

## PyO3 性能扩展

ClawCode 包含一个 Rust 原生性能扩展，用于高速文件操作。

### 组件

| 函数 | 源码 | 用途 |
|------|------|------|
| `grep_path` | `gsd-grep` | 基于 ripgrep 的快速内容搜索 |
| `glob_scan` | `ignore + globset` | 支持 gitignore 的快速文件扫描 |

### 构建

```bash
cd clawcode/clawcode/llm/tools/performance/core/engine-py
pip install maturin
maturin develop --release
```

需要 Rust 工具链。父工作区为 `llm/tools/performance`（`Cargo.toml` 含 `members = ["core/*"]`）。

## 测试套件

| 套件 | 测试数 | 状态 |
|------|--------|------|
| 单元 + 集成 | 833 | ✅ 代理、工具和深度循环回归测试（`max_iters=100`） |
| CLI 参数 | 22 | ✅ CLI 和提供商 `cli_bridge` 路径 |
| 测试工具特性 | 6 | ✅ 多步骤工作流和闭环冒烟测试 |
| Textual TUI | 3 | ✅ 欢迎界面、HUD 覆盖和状态行 |
| TUI 交互 | 27 | ✅ 聊天操作、权限对话框和计划/Arc 面板 |
| 真实技能 + 插件 | 53 | ✅ 内置技能注册/执行和插件沙盒 |

**总计：** 944 项 pytest。**最新完整运行：** 935 通过，9 跳过，0 失败。

### 运行测试

```bash
pytest
ruff check .
mypy .
```

## 架构性能

- **终端原生**：无 IDE 开销，最小内存占用
- **异步 ReAct 循环**：非阻塞工具执行
- **SQLite 持久化**：快速本地会话存储
- **结构化日志**：`structlog` 最小化开销

## 相关文档

| 主题 | 位置 |
|------|------|
| 架构设计 | [architecture.zh.md](./architecture.zh.md) |
| 配置指南 | [clawcode-configuration.md](./clawcode-configuration.md) |
| 代理与团队编排 | [agent-team-orchestration.zh.md](./agent-team-orchestration.zh.md) |
| 项目概述 | [README.zh.md](../README.zh.md) |
