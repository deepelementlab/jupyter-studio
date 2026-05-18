<div align="center">

<!-- <img src="docs/assets/jupyter-studio-logo.png" width="120" alt="Jupyter Studio logo" /> -->
<img width="200" height="180" alt="jupyter-studio-x" src="https://github.com/user-attachments/assets/c0510b68-ad71-4859-935a-729018c0641e" />

# Jupyter Studio

### The AI-Native JupyterLab.
### Open-source **Cursor for Notebooks** — agent inside every cell.

[![Stars](https://img.shields.io/github/stars/deepelementlab/jupyter-studio?style=for-the-badge&color=ffb86c&logo=github)](https://github.com/deepelementlab/jupyter-studio/stargazers)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue?style=for-the-badge)](LICENSE)
[![Release](https://img.shields.io/github/v/release/deepelementlab/jupyter-studio?style=for-the-badge&color=success)](https://github.com/deepelementlab/jupyter-studio/releases)
[![Discussions](https://img.shields.io/github/discussions/deepelementlab/jupyter-studio?style=for-the-badge&logo=github&label=discussions&color=6366f1)](https://github.com/deepelementlab/jupyter-studio/discussions)
[![DeepElementLab](https://img.shields.io/badge/DeepElementLab-organization-111827?style=for-the-badge&logo=github)](https://github.com/deepelementlab)

<!---**[English](README.md)** · **[简体中文](README.zh-CN.md)** · **[Docs](https://github.com/deepelementlab/jupyter-studio/tree/main/docs)** · **[Discussions](https://github.com/deepelementlab/jupyter-studio/discussions)** · **[Roadmap](https://github.com/deepelementlab/jupyter-studio/projects)**-->

<br/>

<img src="docs/assets/hero-demo.gif" width="820" alt="Jupyter Studio Demo" />

<sub><i>Press <kbd>Cmd</kbd>+<kbd>K</kbd> in any cell. Chat with your whole notebook. Let the agent fix the traceback for you.</i></sub>

</div>

---

## ✨ Why Jupyter Studio?

Notebooks are how the world does data science, ML research, and quantitative work — but the AI tooling lives somewhere else. You either jump out to ChatGPT and copy-paste, or you leave Jupyter for an IDE and lose your kernels, plots, and state.

<img width="1200" height="1200" alt="banner" src="https://github.com/user-attachments/assets/e926c327-283d-4a3d-9e5a-c2f4815655e7" />


**Jupyter Studio brings the Cursor-class AI editing experience *into JupyterLab itself*** — same notebook, same kernel, same plots, now with an agent that can read your cells, run them, see the output, and edit them back.


<img width="2606" height="1571" alt="Screenshot - 2026-05-13 17 06 53" src="https://github.com/user-attachments/assets/cecf2d72-d916-4e53-989b-ff0074dc50f3" />

<img width="2606" height="1572" alt="Screenshot - 2026-05-13 17 13 31" src="https://github.com/user-attachments/assets/7e0cf0f0-bd14-478a-97f6-0d05dd56c352" />

- 🧠 **A real agent, not a chatbot** — multi-step plan → execute → verify loop, with cell-level tools (`read_cell`, `edit_cell`, `insert_cell`, `run_cell`, `read_output`).
- ⌨️ **Cmd+K inline edit** — select code, describe the change, accept the diff. Works inside any cell.
- 💬 **Chat that knows your notebook** — `@cell`, `@file`, slash commands, full notebook context, streaming responses.
- 👻 **Ghost Text completion** — Copilot-style inline completion native to JupyterLab.
- 🛠 **Auto-fix tracebacks** — one click on the 🐛 button after an error, the agent diagnoses and patches the cell.
- 🔌 **Bring your own model** — Anthropic, OpenAI, Google, Azure, Ollama, vLLM, any OpenAI-compatible endpoint.
- 🔒 **Local-first & privacy-first** — your code never leaves your machine unless *you* point the agent at a remote model. No telemetry by default.
- 🖥 **Desktop or browser** — ships as a JupyterLab extension *and* a native cross-platform desktop app.

> If you've ever wished JupyterLab had **Cursor / Continue / GitHub Copilot Chat** built in — this is that, free and open source.

---

## 🆚 How does it compare?

|                                  | **Jupyter Studio** | JupyterAI | GitHub Copilot in Jupyter | Cursor | VS Code + Jupyter Ext |
| -------------------------------- | :----------------: | :-------: | :-----------------------: | :----: | :-------------------: |
| Native JupyterLab UI             |         ✅         |    ✅     |             ✅            |   ❌   |          ⚠️          |
| Cmd+K inline edit                |         ✅         |    ❌     |             ⚠️           |   ✅   |          ❌          |
| Ghost-text completion            |         ✅         |    ❌     |             ✅            |   ✅   |          ✅          |
| **Multi-step agent**             |         ✅         |    ⚠️    |             ❌            |   ✅   |          ❌          |
| **Cell-aware tools** (read/edit/run cell) | ✅      |    ❌     |             ❌            |   ❌   |          ❌          |
| Auto-fix traceback               |         ✅         |    ❌     |             ❌            |   ⚠️  |          ❌          |
| Permission gating for risky ops  |         ✅         |    ❌     |             ❌            |   ⚠️  |          ❌          |
| Bring-your-own-model             |         ✅         |    ✅     |             ❌            |   ⚠️  |          ⚠️         |
| Local model support (Ollama/vLLM)|         ✅         |    ✅     |             ❌            |   ❌   |          ⚠️         |
| Self-hosted / fully open-source  |         ✅         |    ✅     |             ❌            |   ❌   |          ⚠️         |
| Free                             |         ✅         |    ✅     |             💲            |   💲  |          ✅         |

> Legend: ✅ first-class · ⚠️ partial / via plugin · ❌ not supported · 💲 paid

---

## ⚡ Quick start

### Option A — One-line installer (recommended)

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/deepelementlab/jupyter-studio/main/install.sh | bash

# Windows (PowerShell)
iwr -useb https://raw.githubusercontent.com/deepelementlab/jupyter-studio/main/install.ps1 | iex
```

This streams the repo’s [`install.sh`](install.sh) / [`install.ps1`](install.ps1) from the `main` branch (adjust the URL if your default branch differs). It creates a venv, installs the server extension, builds the JupyterLab assets, and (optionally) sets up the Open Jupyter desktop shell. The installer is idempotent — run it again any time.

### Option B — Use an existing JupyterLab

```bash
pip install jupyter-studio-ai
jupyter lab
```

That's it. Open any notebook and:

- Press <kbd>Cmd</kbd>/<kbd>Ctrl</kbd> + <kbd>K</kbd> in any cell → inline edit
- Click the ✨ icon in the right sidebar → chat
- Start typing → ghost-text suggestions
- After an error → click 🐛 *Fix with AI*

### Option C — Native desktop app

Download a one-click installer for your OS from the [Releases page](https://github.com/deepelementlab/jupyter-studio/releases/latest):

| Windows 10/11 | macOS 12+ | Linux |
| :---: | :---: | :---: |
| [`.exe`](https://github.com/deepelementlab/jupyter-studio/releases/latest) | [`.dmg` (arm64 / x64)](https://github.com/deepelementlab/jupyter-studio/releases/latest) | [`.deb` / `.rpm` / `.AppImage`](https://github.com/deepelementlab/jupyter-studio/releases/latest) |

---

## 📸 What you can do

<details>
<summary><b>1. Cmd+K in a cell — "make this vectorized"</b></summary>

<img src="docs/assets/demo-cmdk.gif" width="700" alt="Cmd+K demo" />

Select code, hit `Cmd+K`, describe the change in natural language. Accept the diff with `Enter`, reject with `Esc`.
</details>

<details>
<summary><b>2. Agent fixes a traceback in 3 cells</b></summary>

<img src="docs/assets/demo-autofix.gif" width="700" alt="Auto fix demo" />

The agent reads the error, looks at adjacent cells for context, edits the buggy cell, re-runs it, and reports back.
</details>

<details>
<summary><b>3. "Refactor the data loader across cells 3-7"</b></summary>

<img src="docs/assets/demo-refactor.gif" width="700" alt="Refactor demo" />

Multi-cell, multi-step refactors. The agent plans, edits each cell, runs them in order, and tells you what changed.
</details>

<details>
<summary><b>4. Chat with full notebook context using @cell and @file</b></summary>

<img src="docs/assets/demo-chat.gif" width="700" alt="Chat demo" />

`@cell:3` references a specific cell. `@file:data/train.csv` attaches a file. Slash commands like `/explain`, `/test`, `/plot` are first-class.
</details>

---

## 🏗 Architecture

```mermaid
flowchart LR
    subgraph Browser["JupyterLab UI (browser or Open Jupyter desktop)"]
        A1[ai-coder-extension<br/>Cmd+K · Chat · GhostText]
        A2[ai-coder<br/>WS client + reverse RPC]
    end

    subgraph Server["jupyter-server (Python)"]
        B1[Tornado handlers<br/>WS · REST]
        B2[AgentBridge]
        B3[clawcode Agent runtime]
        B4[Jupyter cell tools<br/>read · edit · insert · run]
    end

    subgraph Models["Pluggable model providers"]
        M1[Anthropic]
        M2[OpenAI]
        M3[Google]
        M4[Ollama / vLLM<br/>local]
    end

    A1 <-->|WebSocket| B1
    A2 <-->|reverse RPC| B1
    B1 --> B2 --> B3
    B3 --> B4
    B4 -.->|sharedModel.transact| A2
    B3 --> M1 & M2 & M3 & M4
```

Three packages, one repo:

| Package | What it is |
| --- | --- |
| [`clawcode/`](clawcode/) | The reusable agent runtime: tool calls, multi-step planning, streaming events. Pure Python. |
| [`jupyter_studio_ai/`](jupyter_studio_ai/) | The `jupyter_server` extension: WS/REST endpoints, agent bridge, cell tools. |
| [`open-jupyter/`](open-jupyter/) | The JupyterLab Desktop fork with the `@jupyterlab/ai-coder` and `@jupyterlab/ai-coder-extension` packages preinstalled. |

A deeper dive lives in [`JUPYTERLAB_AI_INTEGRATION.md`](JUPYTERLAB_AI_INTEGRATION.md).

---

## 🔌 Bring Your Own Model

Jupyter Studio AI Coder reads **credentials, provider endpoints, default model slots, and the active coder (`agents.coder`)** from **[ClawCode](https://github.com/deepelementlab/jupyter-studio/tree/main/clawcode)** configuration: a JSON file conventionally named `.clawcode.json`.

### Where Jupyter looks for `.clawcode.json`

The [`jupyter_studio_ai` extension](jupyter_studio_ai/jupyter_studio_ai/extension.py) resolves the config in this **first-hit-wins** order:

1. **`$CLAWCODE_CONFIG`** — absolute path to your JSON file, if set.
2. **`<Jupyter notebook root>/.clawcode.json`** — `jupyter_server`'s `--notebook-dir` / root (the directory you browse in Jupyter).
3. **`<notebook root>/clawcode/.clawcode.json`**
4. **Next to an editable [`clawcode`](clawcode/) install** (e.g. monorepo `clawcode/.clawcode.json` when developing this repo).
5. **`~/.config/clawcode/.clawcode.json`**
6. **`~/.clawcode.json`**

Restart `jupyter lab` after editing the file (or reload the kernel/server) so the extension reloads settings.

### Minimal example (API keys & default model)

Copy and adapt from **[`clawcode/.clawcode_template.json`](clawcode/.clawcode_template.json)** — it lists every provider slot and field. Typical shape:

```json
{
  "providers": {
    "openai": {
      "api_key": "sk-your-key",
      "base_url": null,
      "disabled": false,
      "timeout": 120,
      "models": ["gpt-4o", "gpt-4o-mini"]
    },
    "openai_deepseek": {
      "api_key": "your-deepseek-key",
      "base_url": "https://api.deepseek.com",
      "disabled": false,
      "timeout": 120,
      "models": ["deepseek-chat", "deepseek-reasoner"]
    }
  },
  "agents": {
    "coder": {
      "model": "gpt-4o",
      "provider_key": "openai",
      "max_tokens": 8192,
      "reasoning_effort": "medium",
      "temperature": null
    }
  }
}
```

- **`providers.<slot>`**: one logical gateway (`api_key`, optional `base_url` for OpenAI-compatible APIs, `models` picker list). Set **`disabled`** to omit a slot from the UI.
- **`agents.coder`**: defines the notebook chat / agent default; **`provider_key`** must match a key under **`providers`**.
- The JupyterLab sidebar can **switch models at runtime**; persisting there updates the **coder** entry in `.clawcode.json` when you opt in.

### Env vars & secrets

Prefer putting keys in `.clawcode.json` locally (never commit secrets). Some ClawCode provider paths also honor standard env vars (e.g. `OPENAI_API_KEY` when using the built-in OpenAI slot); see **`clawcode`** config docs inside that package for **`CLAWCODE_*`** conventions.

### Desktop shell (Open Jupyter)

When the desktop app starts Jupyter from a given working directory, **that directory is the notebook root** for lookup **(steps 2–3 above)** unless you point **`CLAWCODE_CONFIG`** at a fixed file globally.


---

## 🛠 Developer quickstart

### Typically, only three steps are needed.

```bash
git clone https://github.com/deepelementlab/jupyter-studio.git
cd jupyter-studio

# Bootstrap everything (venv + python deps + lab build + desktop shell)
./install.sh             # macOS / Linux
./install.ps1            # Windows PowerShell

# Activate the environment, then start Jupyter Studio.
.\.venv\Scripts\Activate.ps1
jupyter lab --dev-mode --notebook-dir="C:\test\jupyter-studio"

```

**Or step-by-step:** if you skip the scripts above, create and activate a virtual environment at the repo root first (default `.venv`, same as `install.ps1`), then run the `pip` / `jlpm` commands below.

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows (PowerShell; if execution policy blocks scripts, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Common Windows pitfalls ( stale `jupyter.exe` paths, Yarn `EISDIR`, why `activate.bat` seems ineffective in PowerShell ) are documented in **[Windows & venv troubleshooting](#windows-venv-troubleshooting)** under *Developer quickstart*.

With the environment activated:

```bash
pip install -e ./clawcode
pip install -e ./jupyter_studio_ai
cd open-jupyter/jupyterlab-main && jlpm install && jlpm run build:dev
jupyter lab --dev-mode
```

See [`dev.md`](open-jupyter/dev.md) for the full developer workflow and [`JUPYTERLAB_AI_INTEGRATION.md`](JUPYTERLAB_AI_INTEGRATION.md) for the integration internals.

<a id="windows-venv-troubleshooting"></a>

### Windows & venv troubleshooting (install.ps1 / dev builds)

**Where `Activate.ps1` comes from.** The installer runs `python -m venv`, which creates `.venv\Scripts\Activate.ps1` (and `activate.bat`, etc.). Those files are part of the standard library’s venv machinery — not handwritten by `install.ps1`.

**PowerShell vs `activate.bat`.** In PowerShell, running `activate.bat` normally starts a short-lived `cmd` child process. When that process exits, **your current PowerShell session is unchanged**, so it looks like “activation did nothing.” Prefer:

```powershell
.\.venv\Scripts\Activate.ps1
```

If scripts are blocked, run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. Alternatively open **Command Prompt** and run `.venv\Scripts\activate.bat`, or call tools without activating: `.\.venv\Scripts\python.exe -m pip …`.

**Manual “activation” without scripts (PowerShell).** For the current terminal only, you can mirror what `Activate.ps1` does (`PATH` + `VIRTUAL_ENV`; the prompt will not show `(.venv)`):

```powershell
$venv = (Resolve-Path .\.venv).Path
$env:VIRTUAL_ENV = $venv
Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
$env:PATH = "$venv\Scripts;$env:PATH"
```

Run these from the repository root; if your virtualenv is not `.venv` (see [`install.ps1`](install.ps1) `-VenvPath`), point `$venv` at that folder instead.

**`jupyter` / `jupyter.exe` still points at another drive (e.g. `D:\…` after cloning to `C:\…`).** On Windows, Pip’s console entry points record the **absolute path to `python.exe` at install time**. Copying a `.venv` folder from another path, or reusing scripts after moving the repo, leaves stale launchers. Symptoms: `Fatal error in launcher: Unable to create process using '"D:\…\python.exe"' …`. Fixes:

- Prefer: **delete `.venv`**, then re-run [`install.ps1`](install.ps1) (or reinstall with `pip`) **only on the final checkout path** — do not copy `.venv` between disks or machines.
- Quick workaround: **`python -m jupyter lab`** (uses the interpreter in the active env and bypasses the broken `jupyter.exe`).
- Or regenerate launchers: `python -m pip install --force-reinstall jupyter-core jupyterlab` inside the active venv.

**Editable JupyterLab install fails during `yarn install` (e.g. `EISDIR` / symlink under `node_modules\@jupyterlab\buildutils`).** The monorepo linker needs directory links; on Windows this often breaks if `open-jupyter/jupyterlab-main/node_modules` is **partially stale** or symlink creation is restricted. Try: delete `jupyterlab-main/node_modules`, turn on **Settings → Privacy & security → For developers → Developer Mode**, then rerun `install.ps1` or `pip install -e open-jupyter/jupyterlab-main[dev]`. Lines like `YN0002` peer-dependency hints from Yarn are usually **noise** and not the root failure.


<img width="2333" height="1496" alt="Screenshot - 2026-05-14 13 05 23" src="https://github.com/user-attachments/assets/5c6e03ac-361b-46ba-97a7-54d00a8d0fee" />

---

## 🗺 Roadmap

- [x] Cmd+K inline edit
- [x] Chat sidebar with `@cell` / `@file` context
- [x] Ghost-text completion
- [x] Multi-step agent with cell tools
- [x] Auto-fix tracebacks
- [x] Cross-platform desktop installer
- [ ] **Notebook-level diff & checkpoint** (Q2)
- [ ] **Variable inspector tool for the agent** (Q2)
- [ ] **Collaborative agent in RTC notebooks** (Q3)
- [ ] **Custom skill packs** (Q3)
- [ ] **VS Code parity for `.py` files inside Lab** (Q4)

Track everything live on the [public roadmap →](https://github.com/deepelementlab/jupyter-studio/projects)

---

## 🤝 Contributing

We love contributors. There are **[good-first-issues here](https://github.com/deepelementlab/jupyter-studio/labels/good%20first%20issue)** — most can be done in under 100 lines of code.

- 🐛 [Report a bug](https://github.com/deepelementlab/jupyter-studio/issues/new?template=bug.yml)
- 💡 [Request a feature](https://github.com/deepelementlab/jupyter-studio/issues/new?template=feature.yml)
- 📖 [Improve the docs](https://github.com/deepelementlab/jupyter-studio/tree/main/docs)
- 💬 [GitHub Discussions](https://github.com/deepelementlab/jupyter-studio/discussions) — ask questions and share ideas

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before you open a PR. Be kind, ship code, have fun.

---

## 💖 Sponsors & Used by

> *Logos appear here once your sponsors / users opt in.*

If your team relies on Jupyter Studio in production, we'd love to feature you. Open a PR adding your logo to [`docs/users.md`](docs/users.md), or [sponsor DeepElementLab on GitHub](https://github.com/sponsors/deepelementlab).

---

## ⭐ Star History

<a href="https://star-history.com/#deepelementlab/jupyter-studio&Date">
  <img src="https://api.star-history.com/svg?repos=deepelementlab/jupyter-studio&type=Date" alt="Star History Chart" width="640" />
</a>

If Jupyter Studio saves you time, **[give it a star ⭐](https://github.com/deepelementlab/jupyter-studio)** — it genuinely helps more people discover the project.

---

## 📄 License & citation

Released under the **Apache 2.0 License**. See [`LICENSE`](LICENSE).

If you use Jupyter Studio in academic work, please cite:

```bibtex
@software{jupyter_studio_2026,
  title  = {Jupyter Studio: An AI-native JupyterLab},
  author = {The Jupyter Studio Authors},
  year   = {2026},
  url    = {https://github.com/deepelementlab/jupyter-studio}
}
```

---

<div align="center">

**Built by notebook nerds, for notebook nerds.**

<!--[Repository](https://github.com/deepelementlab/jupyter-studio) · [Docs tree](https://github.com/deepelementlab/jupyter-studio/tree/main/docs) · [Discussions](https://github.com/deepelementlab/jupyter-studio/discussions) · [Releases](https://github.com/deepelementlab/jupyter-studio/releases) · [Organization](https://github.com/deepelementlab)-->

[Repository](https://github.com/deepelementlab/jupyter-studio) · [Organization](https://github.com/deepelementlab)

</div>
