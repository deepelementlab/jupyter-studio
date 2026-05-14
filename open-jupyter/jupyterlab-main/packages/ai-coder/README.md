# @jupyterlab/ai-coder

Library used by [`@jupyterlab/ai-coder-extension`](../ai-coder-extension/) to
talk to the [`jupyter_studio_ai`](../../../../jupyter_studio_ai/) server
extension.

This package contains:

- `tokens` — Dependency injection tokens (`IAiCoderService`).
- `models` — TS mirror of the wire protocol defined in
  `jupyter_studio_ai/jupyter_studio_ai/models.py`.
- `transport` — `AiTransport` WebSocket client + reverse RPC dispatcher.
- `service` — `AiCoderService`, one session per `NotebookPanel`.
- `notebookOps` — Implements the reverse RPC methods (read/edit/insert/run
  cells) against the live JupyterLab notebook model using yjs shared model
  transactions.
