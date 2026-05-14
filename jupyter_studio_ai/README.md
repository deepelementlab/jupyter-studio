# jupyter_studio_ai

JupyterLab server extension that exposes the [clawcode](../clawcode/) coder agent
as an AI assistant for notebooks. Pairs with the front-end packages
`@jupyterlab/ai-coder` and `@jupyterlab/ai-coder-extension` in
`open-jupyter/jupyterlab-main/packages/`.

## Architecture

```
Browser (JupyterLab UI)
  │  WebSocket  /jupyter-studio-ai/ws/<session_id>
  │  REST       /jupyter-studio-ai/inline/{complete,edit}
  │  REST       /jupyter-studio-ai/sessions
  ▼
Tornado handlers (jupyter_studio_ai.handlers.*)
  ▼
AgentBridge  ──►  clawcode CoderRuntimeBundle  ──►  clawcode Agent
                       │
                       ├── builtin clawcode tools (view/edit/bash/grep/glob/Agent/TodoWrite ...)
                       └── jupyter cell tools (read/edit/insert/delete/run cell)
                              │
                              ▼
                       NotebookRpc  ──►  reverse-call front-end via WebSocket
```

## Install

```bash
pip install -e .
jupyter lab
```

The extension auto-registers via
`jupyter-config/jupyter_server_config.d/jupyter_studio_ai.json`.

## Endpoints

| Path | Verb | Purpose |
|------|------|---------|
| `/jupyter-studio-ai/ws/<session_id>` | WS | Bi-directional agent stream + reverse RPC |
| `/jupyter-studio-ai/inline/complete` | POST | Short Ghost Text completion |
| `/jupyter-studio-ai/inline/edit` | POST | Short Cmd+K edit generation |
| `/jupyter-studio-ai/sessions` | GET/POST/DELETE | Manage sessions |
| `/jupyter-studio-ai/health` | GET | Liveness/version |
