// Copyright (c) Jupyter Studio AI.
// Distributed under the terms of the Modified BSD License.

import { INotebookTracker, NotebookPanel } from '@jupyterlab/notebook';
import { ServerConnection } from '@jupyterlab/services';
import { Signal } from '@lumino/signaling';
import { DisposableDelegate, DisposableSet, IDisposable } from '@lumino/disposable';

import {
  AgentEventOut,
  CoderInfo,
  ErrorOut,
  InlineCompleteRequest,
  InlineEditRequest,
  ModelsResponse,
  PermissionRequestOut
} from './models';
import { bindNotebookOps, buildNotebookStateFrame } from './notebookOps';
import { IAgentTurn, IAiCoderService, IRunUserMessageOptions } from './tokens';
import { AiTransport } from './transport';

interface ISessionEntry {
  transport: AiTransport;
  turns: IAgentTurn[];
  activeTurn: IAgentTurn | null;
  disposables: DisposableSet;
}

/**
 * Concrete implementation of :class:`IAiCoderService`.
 *
 * One :class:`AiTransport` per opened :class:`NotebookPanel` (lazy). Closing
 * the panel disposes the transport.
 */
export class AiCoderService implements IAiCoderService, IDisposable {
  constructor(opts: {
    tracker: INotebookTracker;
    settings?: ServerConnection.ISettings;
  }) {
    this._tracker = opts.tracker;
    this._settings = opts.settings ?? ServerConnection.makeSettings();
    this._tracker.widgetAdded.connect(this._onWidgetAdded, this);
  }

  // -- Signals -----------------------------------------------------------------

  readonly agentEvent = new Signal<
    this,
    { panel: NotebookPanel; event: AgentEventOut }
  >(this);
  readonly permissionRequest = new Signal<
    this,
    { panel: NotebookPanel; request: PermissionRequestOut }
  >(this);
  readonly turnComplete = new Signal<this, { panel: NotebookPanel; turn: IAgentTurn }>(
    this
  );
  readonly sessionReady = new Signal<this, NotebookPanel>(this);
  readonly coderChanged = new Signal<this, CoderInfo>(this);

  get currentCoder(): CoderInfo | null {
    return this._currentCoder;
  }

  // -- Lifecycle ---------------------------------------------------------------

  get isDisposed(): boolean {
    return this._disposed;
  }

  dispose(): void {
    if (this._disposed) {
      return;
    }
    this._disposed = true;
    for (const entry of this._sessions.values()) {
      void entry.transport.disconnect();
      entry.disposables.dispose();
    }
    this._sessions.clear();
    if (this._rest) {
      void this._rest.disconnect();
      this._rest = null;
    }
    Signal.clearData(this);
  }

  // -- Public API --------------------------------------------------------------

  async runUserMessage(opts: IRunUserMessageOptions): Promise<void> {
    const entry = await this._ensureSession(opts.panel);
    const turn: IAgentTurn = {
      id: `t_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`,
      userText: opts.text,
      events: [],
      startedAt: Date.now(),
      finishedAt: null,
      isError: false
    };
    entry.turns.push(turn);
    entry.activeTurn = turn;

    // Notify the panel that a new turn started so the user's own message
    // appears immediately, even before the back-end yields any agent_event.
    // Using a synthetic ``thinking`` event keeps the existing rendering path
    // (TurnView reads ``turn.events``) without bolting on a new signal.
    this.agentEvent.emit({
      panel: opts.panel,
      event: {
        kind: 'agent_event',
        event_type: 'thinking',
        content: ''
      }
    });

    const snap = buildNotebookStateFrame(opts.panel);
    await entry.transport.sendNotebookSnapshot(
      snap.cells,
      snap.notebookPath,
      snap.activeCellIndex
    );
    await entry.transport.sendUserMessage({
      text: opts.text,
      cell_refs: opts.cellRefs,
      file_refs: opts.fileRefs,
      notebook_path: snap.notebookPath,
      plan_mode: opts.planMode
    });
  }

  async generateInline(req: InlineCompleteRequest): Promise<string> {
    const transport = new AiTransport('__inline__', this._settings);
    const resp = await transport.inlineComplete(req);
    return resp.text;
  }

  async editInline(req: InlineEditRequest): Promise<string> {
    const transport = new AiTransport('__inline__', this._settings);
    const resp = await transport.inlineEdit(req);
    return resp.text;
  }

  async cancel(panel: NotebookPanel): Promise<void> {
    const entry = this._sessions.get(panel);
    if (entry) {
      await entry.transport.sendCancel();
    }
  }

  async decidePermission(
    panel: NotebookPanel,
    requestId: string,
    decision: 'grant' | 'deny' | 'grant_session'
  ): Promise<void> {
    const entry = this._sessions.get(panel);
    if (entry) {
      await entry.transport.sendPermissionDecision({
        request_id: requestId,
        decision
      });
    }
  }

  getTurns(panel: NotebookPanel): IAgentTurn[] {
    return this._sessions.get(panel)?.turns ?? [];
  }

  async listModels(): Promise<ModelsResponse> {
    const transport = this._restTransport();
    const response = await transport.listModels();
    this._currentCoder = response.current;
    this.coderChanged.emit(response.current);
    return response;
  }

  async setCoderModel(opts: {
    model: string;
    providerKey?: string | null;
    persist?: boolean;
  }): Promise<CoderInfo> {
    const transport = this._restTransport();
    const info = await transport.setCoder({
      model: opts.model,
      provider_key: opts.providerKey ?? null,
      persist: opts.persist ?? false
    });
    this._currentCoder = info;
    this.coderChanged.emit(info);
    return info;
  }

  // -- Internals --------------------------------------------------------------

  private _restTransport(): AiTransport {
    // REST-only calls don't need a session-bound WebSocket; we reuse a single
    // throwaway transport keyed on a sentinel so the underlying ServerConnection
    // settings (baseUrl/wsUrl/auth) are picked up from the same source.
    if (!this._rest) {
      this._rest = new AiTransport('__rest__', this._settings);
    }
    return this._rest;
  }

  private async _ensureSession(panel: NotebookPanel): Promise<ISessionEntry> {
    let entry = this._sessions.get(panel);
    if (entry) {
      return entry;
    }
    const sessionKey = this._sessionKey(panel);
    const transport = new AiTransport(sessionKey, this._settings);
    const disposables = new DisposableSet();

    const onEvent = (_: AiTransport, ev: AgentEventOut) => {
      const cur = entry!.activeTurn;
      if (cur) {
        cur.events.push(ev);
        if (
          ev.event_type === 'response' ||
          ev.event_type === 'error' ||
          ev.done
        ) {
          cur.finishedAt = Date.now();
          cur.isError = ev.event_type === 'error' || !!ev.is_error;
          this.turnComplete.emit({ panel, turn: cur });
          entry!.activeTurn = null;
        }
      }
      this.agentEvent.emit({ panel, event: ev });
    };
    const onPerm = (_: AiTransport, req: PermissionRequestOut) => {
      this.permissionRequest.emit({ panel, request: req });
    };
    const onReady = () => this.sessionReady.emit(panel);

    // WS-level ``{kind:"error", message:"..."}`` frames (e.g. ``"session
    // busy"`` when the user sends a second message before the first finishes,
    // or invalid-JSON / unknown-kind responses) were previously dropped on
    // the floor: the picker would never know the turn ended and the Send
    // button stayed in "Stop" state forever (or in the busy-flip case, it
    // would silently revert to Send without surfacing why). Translate them
    // into a synthetic ``agent_event`` so the existing turn-complete +
    // error rendering path picks them up.
    const onErrored = (_: AiTransport, err: ErrorOut) => {
      const cur = entry!.activeTurn;
      const synthetic: AgentEventOut = {
        kind: 'agent_event',
        event_type: 'error',
        error: err.message || 'unknown error',
        done: true,
        is_error: true
      };
      if (cur) {
        cur.events.push(synthetic);
        cur.finishedAt = Date.now();
        cur.isError = true;
        this.turnComplete.emit({ panel, turn: cur });
        entry!.activeTurn = null;
      }
      this.agentEvent.emit({ panel, event: synthetic });
    };

    transport.agentEvent.connect(onEvent);
    transport.permissionRequest.connect(onPerm);
    transport.connected.connect(onReady);
    transport.errored.connect(onErrored);

    disposables.add(
      new DisposableDelegate(() => {
        transport.agentEvent.disconnect(onEvent);
        transport.permissionRequest.disconnect(onPerm);
        transport.connected.disconnect(onReady);
        transport.errored.disconnect(onErrored);
      })
    );

    bindNotebookOps(transport, () => panel);

    entry = {
      transport,
      turns: [],
      activeTurn: null,
      disposables
    };
    this._sessions.set(panel, entry);

    await transport.connect();
    return entry;
  }

  private _onWidgetAdded(_: INotebookTracker, panel: NotebookPanel): void {
    panel.disposed.connect(() => {
      const entry = this._sessions.get(panel);
      if (entry) {
        entry.disposables.dispose();
        void entry.transport.disconnect();
        this._sessions.delete(panel);
      }
    });
  }

  private _sessionKey(panel: NotebookPanel): string {
    // ``notebook_path`` keeps the agent state persistent across reloads of the
    // same notebook; falling back to widget id when path is missing (e.g. a
    // freshly created untitled).
    return panel.context?.path || panel.id || 'untitled';
  }

  private _tracker: INotebookTracker;
  private _settings: ServerConnection.ISettings;
  private _sessions = new Map<NotebookPanel, ISessionEntry>();
  private _disposed = false;
  private _rest: AiTransport | null = null;
  private _currentCoder: CoderInfo | null = null;
}
