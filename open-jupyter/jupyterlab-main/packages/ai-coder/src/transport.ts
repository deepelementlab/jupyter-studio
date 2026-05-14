// Copyright (c) Jupyter Studio AI.
// Distributed under the terms of the Modified BSD License.
//
// WebSocket + REST client for jupyter_studio_ai.

import { URLExt } from '@jupyterlab/coreutils';
import { ServerConnection } from '@jupyterlab/services';
import { Signal, ISignal } from '@lumino/signaling';

import {
  AgentEventOut,
  CoderInfo,
  ErrorOut,
  InlineCompleteRequest,
  InlineCompleteResponse,
  InlineEditRequest,
  InlineEditResponse,
  ModelsResponse,
  PermissionDecisionIn,
  PermissionRequestOut,
  ReadyOut,
  SetCoderRequest,
  ToolRequestOut,
  ToolResponseIn,
  UserMessageIn,
  WsInbound,
  WsOutbound
} from './models';

const NAMESPACE = 'jupyter-studio-ai';

/**
 * Handler signature for reverse RPC requests dispatched by the back-end.
 */
export type RpcHandler = (
  params: Record<string, unknown>
) => Promise<unknown>;

export class AiTransport {
  constructor(
    public readonly sessionId: string,
    settings?: ServerConnection.ISettings
  ) {
    this._settings = settings ?? ServerConnection.makeSettings();
  }

  // ---------------------------------------------------------------------------
  // Signals
  // ---------------------------------------------------------------------------

  get agentEvent(): ISignal<this, AgentEventOut> {
    return this._agentEvent;
  }
  get permissionRequest(): ISignal<this, PermissionRequestOut> {
    return this._permissionRequest;
  }
  get connected(): ISignal<this, ReadyOut> {
    return this._connected;
  }
  get errored(): ISignal<this, ErrorOut> {
    return this._errored;
  }
  get closed(): ISignal<this, void> {
    return this._closed;
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  /**
   * Register a reverse-RPC handler (e.g. ``readCell``). The browser implements
   * the actual notebook mutation; the back-end invokes it through here.
   */
  registerRpc(method: string, handler: RpcHandler): void {
    this._handlers.set(method, handler);
  }

  /**
   * Open the WebSocket. Returns a promise resolved on ``ready``.
   */
  async connect(): Promise<void> {
    if (this._ws && this._ws.readyState !== WebSocket.CLOSED) {
      return this._readyPromise;
    }
    const wsUrl = URLExt.join(
      this._settings.wsUrl,
      NAMESPACE,
      'ws',
      encodeURIComponent(this.sessionId)
    );
    const ctor = (this._settings.WebSocket || WebSocket) as typeof WebSocket;
    const ws = new ctor(wsUrl);
    this._ws = ws;
    this._readyPromise = new Promise<void>((resolve, reject) => {
      const onReady = (_: AiTransport, ready: ReadyOut) => {
        if (ready.session_id) {
          this._connected.disconnect(onReady, this);
          resolve();
        }
      };
      this._connected.connect(onReady, this);
      ws.onerror = () => reject(new Error('AiTransport: WebSocket error'));
      ws.onclose = () => this._closed.emit();
    });
    ws.onmessage = ev => {
      try {
        this._dispatch(JSON.parse(ev.data) as WsOutbound);
      } catch (err) {
        console.warn('AiTransport: invalid frame', err);
      }
    };
    return this._readyPromise;
  }

  async disconnect(): Promise<void> {
    if (this._ws) {
      try {
        this._ws.close();
      } catch {
        /* ignore */
      }
      this._ws = null;
    }
  }

  async sendUserMessage(payload: Omit<UserMessageIn, 'kind'>): Promise<void> {
    return this._send({ kind: 'user_message', ...payload });
  }

  async sendCancel(): Promise<void> {
    return this._send({ kind: 'cancel' });
  }

  async sendPermissionDecision(
    payload: Omit<PermissionDecisionIn, 'kind'>
  ): Promise<void> {
    return this._send({ kind: 'permission_decision', ...payload });
  }

  async sendNotebookSnapshot(
    cells: Array<{
      index: number;
      cell_type: 'code' | 'markdown' | 'raw';
      source_preview: string;
      execution_count: number | null;
      has_output: boolean;
    }>,
    notebookPath: string | null,
    activeCellIndex: number | null
  ): Promise<void> {
    return this._send({
      kind: 'notebook_state',
      notebook_path: notebookPath,
      cells,
      active_cell_index: activeCellIndex
    });
  }

  /**
   * Stateless inline completion (Ghost Text).
   */
  async inlineComplete(
    req: InlineCompleteRequest
  ): Promise<InlineCompleteResponse> {
    return this._postJson('inline/complete', req);
  }

  /**
   * Stateless inline edit (Cmd+K).
   */
  async inlineEdit(req: InlineEditRequest): Promise<InlineEditResponse> {
    return this._postJson('inline/edit', req);
  }

  /**
   * List configured provider slots + currently bound coder agent.
   */
  async listModels(): Promise<ModelsResponse> {
    return this._getJson('models');
  }

  /**
   * Snapshot of the currently bound coder agent.
   */
  async getCoder(): Promise<CoderInfo> {
    return this._getJson('coder');
  }

  /**
   * Hot-swap the coder agent. The bridge rebuilds its runtime so the next
   * chat / Ghost Text / Cmd+K call goes through the new provider.
   */
  async setCoder(req: SetCoderRequest): Promise<CoderInfo> {
    return this._postJson('coder', req);
  }

  // ---------------------------------------------------------------------------
  // Internals
  // ---------------------------------------------------------------------------

  private async _send(frame: WsInbound): Promise<void> {
    if (!this._ws) {
      await this.connect();
    }
    await this._readyPromise;
    this._ws!.send(JSON.stringify(frame));
  }

  private async _postJson<T>(path: string, body: unknown): Promise<T> {
    const url = URLExt.join(this._settings.baseUrl, NAMESPACE, path);
    const response = await ServerConnection.makeRequest(
      url,
      {
        method: 'POST',
        body: JSON.stringify(body),
        headers: { 'Content-Type': 'application/json' }
      },
      this._settings
    );
    if (!response.ok) {
      let message = `${path} failed: ${response.status}`;
      try {
        const text = await response.text();
        if (text) {
          message += ` ${text.slice(0, 500)}`;
        }
      } catch {
        /* ignore */
      }
      throw new Error(message);
    }
    return (await response.json()) as T;
  }

  private async _getJson<T>(path: string): Promise<T> {
    const url = URLExt.join(this._settings.baseUrl, NAMESPACE, path);
    const response = await ServerConnection.makeRequest(
      url,
      { method: 'GET' },
      this._settings
    );
    if (!response.ok) {
      throw new Error(`${path} failed: ${response.status}`);
    }
    return (await response.json()) as T;
  }

  private async _dispatch(frame: WsOutbound): Promise<void> {
    switch (frame.kind) {
      case 'ready':
        this._connected.emit(frame);
        return;
      case 'error':
        this._errored.emit(frame);
        return;
      case 'agent_event':
        this._agentEvent.emit(frame);
        return;
      case 'permission_request':
        this._permissionRequest.emit(frame);
        return;
      case 'pong':
        return;
      case 'tool_request': {
        await this._handleToolRequest(frame);
        return;
      }
      default:
        // exhaustive
        return;
    }
  }

  private async _handleToolRequest(frame: ToolRequestOut): Promise<void> {
    const handler = this._handlers.get(frame.method);
    let body: ToolResponseIn;
    if (!handler) {
      body = {
        kind: 'tool_response',
        request_id: frame.request_id,
        is_error: true,
        error_message: `no handler for ${frame.method}`
      };
    } else {
      try {
        const result = await handler(frame.params || {});
        body = {
          kind: 'tool_response',
          request_id: frame.request_id,
          result
        };
      } catch (err) {
        body = {
          kind: 'tool_response',
          request_id: frame.request_id,
          is_error: true,
          error_message: err instanceof Error ? err.message : String(err)
        };
      }
    }
    try {
      this._ws?.send(JSON.stringify(body));
    } catch {
      /* socket likely closed */
    }
  }

  private _settings: ServerConnection.ISettings;
  private _ws: WebSocket | null = null;
  private _readyPromise: Promise<void> = Promise.resolve();
  private _agentEvent = new Signal<this, AgentEventOut>(this);
  private _permissionRequest = new Signal<this, PermissionRequestOut>(this);
  private _connected = new Signal<this, ReadyOut>(this);
  private _errored = new Signal<this, ErrorOut>(this);
  private _closed = new Signal<this, void>(this);
  private _handlers = new Map<string, RpcHandler>();
}
