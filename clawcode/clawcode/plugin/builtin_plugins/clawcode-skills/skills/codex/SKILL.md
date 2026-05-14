---
name: codex
description: Delegate coding tasks to the OpenAI Codex CLI for features, refactoring, PR reviews, and batch fixes. Requires the codex CLI and typically a git repository.
version: 1.0.0
license: MIT
metadata:
  clawcode:
    tags: [Coding-Agent, Codex, OpenAI, Code-Review, Refactoring]
    related_skills: [coding-standards, python-patterns, opencode]
---

# Codex CLI (clawcode)

Use [OpenAI Codex](https://github.com/openai/codex) as an external coding agent when the user wants Codex specifically.

**Do not confuse these entry points** (they are not interchangeable):

| Entry | Role |
|-------|------|
| **`/codex-cli`** (TUI slash) | **One-shot** probe or command via [`codex_cli_bridge`](../../../../../llm/claw_support/codex_cli_bridge.py): merged stdout/stderr, **not** a PTY session and **not** multi-turn TUI control. Default args often `--version`. |
| **`bash`** | One-shot shell in agent turns, e.g. `codex exec '…'`. |
| **`terminal`** + **`process`** (Agent tools) | **Multi-turn** driving of Codex: `terminal` with `background=true` (and `pty=true` on POSIX with `clawcode[terminal-pty]`), then `process` for `poll` / `submit` / `kill`. **Codex expects a git repo**; for scratch dirs use `mktemp -d && git init`. **Windows** local PTY is limited—full TUI automation use **WSL/Linux**. |

Optional: `pip install 'clawcode[terminal-pty]'` for `ptyprocess` on POSIX.

## Prerequisites

- Install Codex: `npm install -g @openai/codex` (command name `codex` on `PATH`).
- Configure OpenAI credentials per Codex docs (API key / auth).
- **Git repository** — many Codex flows refuse to run outside a repo; use a temp dir + `git init` for greenfield scratch.

## When to use

- User asks for Codex or `codex` explicitly.
- You need a bounded task: prefer `codex exec '...'` via **bash** in the project workspace.
- Quick install check: **`/codex-cli`** after **`/claw`** (default `codex --version`); same terminal stack as **`/claude-cli`** / **`/opencode-cli`**.

## clawcode-specific capabilities

| Goal | What to use |
|------|---------------|
| **Quick probe** | **`/codex-cli`** only—single run, not multi-run TUI. |
| **One-shot exec** | **`bash`** or **`terminal`** foreground: `codex exec 'task'` with `working_directory` in a git repo. |
| **Long / background** | **`terminal`** (`background=true`, `pty=true` where supported) + **`process`**. Optional **`check_interval`** on `terminal` for TUI completion notifications (see `CLAW_SUPPORT_MAP.md`). |

## One-shot examples (foreground)

```
terminal(command="codex exec 'Add dark mode toggle to settings'", workdir="~/project", pty=true)
```

Scratch with new repo:

```
terminal(command="cd $(mktemp -d) && git init && codex exec 'Build a snake game in Python'", pty=true)
```

## Background mode

```
terminal(command="codex exec --full-auto 'Refactor the auth module'", workdir="~/project", background=true, pty=true)
process(action="poll", session_id="<id>")
process(action="log", session_id="<id>")
process(action="submit", session_id="<id>", data="yes")
process(action="kill", session_id="<id>")
```

## Key flags (Codex upstream)

| Flag | Effect |
|------|--------|
| `exec "prompt"` | One-shot run, exits when done |
| `--full-auto` | Sandboxed; auto-approves file changes in workspace |
| `--yolo` | No sandbox (dangerous; use with care) |

## Rules

1. Prefer **`pty=true`** for interactive Codex sessions on POSIX; without PTY many CLIs misbehave.
2. Respect **git repo** requirements; document when you create a throwaway repo.
3. **`/codex-cli`** does not replace **`terminal`/`process`** for long interactive work.
