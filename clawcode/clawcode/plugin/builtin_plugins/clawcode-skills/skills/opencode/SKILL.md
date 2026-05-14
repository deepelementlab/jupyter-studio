---
name: opencode
description: Delegate coding tasks to the OpenCode CLI for feature work, refactoring, PR review, and autonomous-style runs. Requires opencode installed where the agent can execute shell commands.
version: 1.0.0
license: MIT
metadata:
  clawcode:
    tags: [Coding-Agent, OpenCode, CLI, Refactoring]
    related_skills: [coding-standards, python-patterns, codex]
---

# OpenCode CLI (clawcode)

Use [OpenCode](https://opencode.ai) as an external coding agent when the user wants OpenCode specifically.

**Do not confuse these entry points** (they are not interchangeable):

| Entry | Role |
|-------|------|
| **`/opencode-cli`** (TUI slash) | **One-shot** probe or command via [`opencode_cli_bridge`](../../../../../llm/claw_support/opencode_cli_bridge.py): merged stdout/stderr, **not** a PTY session and **not** multi-turn TUI control. Default args often `--version`. |
| **`bash`** | One-shot shell in agent turns, e.g. `opencode run '…'`. |
| **`terminal`** + **`process`** (Agent tools) | **Multi-turn** driving of a background shell/OpenCode TUI: `terminal` with `background=true` (and `pty=true` on POSIX with `clawcode[terminal-pty]`), then `process` for `poll` / `submit` / `kill`. Requires `CLAWCODE_TERMINAL_ENV=local` for full PTY on Linux/macOS; **Windows host** is limited—use **WSL or Linux** for interactive TUI automation. |

Optional: `pip install 'clawcode[terminal-pty]'` for `ptyprocess` on POSIX.

## When to use

- User asks to use OpenCode or `opencode`.
- You need a bounded task: prefer `opencode run '...'` via **bash** in the project workspace.
- You only need to verify the CLI is installed: **`/opencode-cli`** (default `opencode --version`) after **`/claw`**; same terminal stack as **`/claude-cli`** (`CLAWCODE_TERMINAL_ENV` / `TERMINAL_ENV`).

## Prerequisites

- Install OpenCode (e.g. `npm i -g opencode-ai@latest` or vendor instructions).
- Auth: `opencode auth login` or provider env vars (see OpenCode docs).
- Check: `opencode auth list` should list at least one provider when run in the same environment as the agent.

## clawcode-specific capabilities

| Goal | What to use |
|------|-------------|
| **Quick probe** (version, install check) | **`/opencode-cli`** only—single run, not multi-turn. Same Claw gate as `/claude-cli`. |
| **Run a command** in agent turns | **`bash`**: e.g. `opencode run 'your task'` with `working_directory` set to the repo root. |
| **Docker/SSH terminal backend** | Same as bash: `settings.shell.use_environments_backend` and `CLAWCODE_TERMINAL_*`; ensure the image or remote has `opencode` on `PATH`. |
| **Interactive OpenCode TUI (agent-driven)** | **`terminal`** (`background=true`, `pty=true` where supported) + **`process`** (`poll` / `submit` / …). Non-local backends: log-polled background only (no stdin). Optional **`check_interval`** on `terminal` schedules completion notifications in the TUI (see `CLAW_SUPPORT_MAP.md`). |

## One-shot tasks (recommended)

Use `opencode run` for bounded work:

```bash
opencode run 'Add retry logic to API calls and update tests'
```

Attach files with `-f` when needed. Use `--thinking`, `--model`, etc. per OpenCode CLI help.

## Binary resolution

If `which opencode` differs between environments, use an absolute path in the bash command:

```bash
"$HOME/.opencode/bin/opencode" run '...'
```

## Pitfalls

- On **Windows**, prefer WSL/Linux for full PTY TUI automation; pipe mode or non-local sandboxes do not match a full local PTY.
- Interactive `opencode` still benefits from a real user terminal for some UX; **bash** alone does not replace PTY driving.
- `opencode` exit codes and stderr: see bash tool output; **`/opencode-cli`** shows stdout/stderr blocks in the chat UI.
- Avoid `/exit` in OpenCode TUI (invalid per OpenCode UX); prefer Ctrl+C in a real terminal session.

## Verification

```bash
opencode --version
opencode run 'Respond with exactly: OPENCODE_SMOKE_OK'
```

## Rules

1. Prefer `opencode run` for automation.
2. Scope work to a single repo root per task when possible.
3. Use **`/opencode-cli`** only for quick checks or demos; heavy work goes through **bash** with explicit commands.
