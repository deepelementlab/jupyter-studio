// Copyright (c) Jupyter Studio AI.

import {
  AgentEventOut,
  CoderInfo,
  IAiCoderService,
  PermissionRequestOut,
  ProviderInfo
} from '@jupyterlab/ai-coder';
import type { IRenderMimeRegistry } from '@jupyterlab/rendermime';
import { ReactWidget } from '@jupyterlab/ui-components';
import { INotebookTracker, NotebookPanel } from '@jupyterlab/notebook';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';
import * as React from 'react';

import {
  applySlashCommand,
  parseReferences,
  SLASH_COMMANDS
} from '../utils';

import { MarkdownView } from './MarkdownView';
import { ModelPicker } from './ModelPicker';
import { reduceStreamEvents, StreamItem } from './streamReducer';
import {
  estimateTokens,
  readThinkingDefaultOpen,
  writeThinkingDefaultOpen
} from './thinkingPrefs';

const MAX_RENDERED_TURNS = 80;

interface ChatPanelProps {
  service: IAiCoderService;
  tracker: INotebookTracker;
  translator: ITranslator;
  rendermime: IRenderMimeRegistry | null;
}

interface ChatPanelState {
  panel: NotebookPanel | null;
  input: string;
  // bumped to force re-render when service signals fire
  rev: number;
  pendingPermissions: PermissionRequestOut[];
  busy: boolean;
  coder: CoderInfo | null;
  providers: ProviderInfo[];
  modelsError: string | null;
}

class ChatPanelComponent extends React.Component<ChatPanelProps, ChatPanelState> {
  state: ChatPanelState = {
    panel: this.props.tracker.currentWidget,
    input: '',
    rev: 0,
    pendingPermissions: [],
    busy: false,
    coder: this.props.service.currentCoder,
    providers: [],
    modelsError: null
  };

  componentDidMount(): void {
    const { service, tracker } = this.props;
    tracker.currentChanged.connect(this._onCurrentChanged, this);
    service.agentEvent.connect(this._onAgentEvent, this);
    service.permissionRequest.connect(this._onPermission, this);
    service.turnComplete.connect(this._onTurnComplete, this);
    service.coderChanged.connect(this._onCoderChanged, this);
    void this._loadModelsWithRetry();
  }

  componentWillUnmount(): void {
    this._unmounted = true;
    if (this._retryTimer !== null) {
      window.clearTimeout(this._retryTimer);
      this._retryTimer = null;
    }
    const { service, tracker } = this.props;
    tracker.currentChanged.disconnect(this._onCurrentChanged, this);
    service.agentEvent.disconnect(this._onAgentEvent, this);
    service.permissionRequest.disconnect(this._onPermission, this);
    service.turnComplete.disconnect(this._onTurnComplete, this);
    service.coderChanged.disconnect(this._onCoderChanged, this);
  }

  /**
   * The bridge is constructed lazily on jupyter_server's first IOLoop tick,
   * so the very first ``GET /models`` after a fresh lab startup may return
   * 503. On slow Windows machines (cold venv, --dev-mode) this can take
   * tens of seconds. Retry generously before surfacing the error so the
   * picker doesn't render empty for the entire session.
   *
   * Also treat raw network errors (``Failed to fetch`` / ``ECONNREFUSED``)
   * as transient: during cold startup the server can briefly accept TCP
   * before the websocket / route is wired up, producing a fetch failure
   * indistinguishable from a transient 503.
   */
  private _loadModelsWithRetry = async (): Promise<void> => {
    // Total budget ~60s. Long enough to outlast even a slow cold start
    // of jupyter --dev-mode + initial bridge construction.
    const delays = [
      400, 800, 1500, 2500, 4000, 6000, 8000, 10000, 12000, 15000
    ];
    for (let attempt = 0; attempt <= delays.length; attempt++) {
      if (this._unmounted) return;
      try {
        const resp = await this.props.service.listModels();
        if (this._unmounted) return;
        this.setState({
          providers: resp.providers,
          coder: resp.current,
          modelsError: null
        });
        return;
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        const transient =
          /\b(503|404|bridge not ready)\b/i.test(msg) ||
          /failed to fetch|networkerror|ECONNREFUSED|ENOTFOUND|ETIMEDOUT/i.test(
            msg
          );
        if (!transient || attempt === delays.length) {
          if (!this._unmounted) {
            this.setState({ modelsError: msg });
          }
          return;
        }
        await new Promise<void>(resolve => {
          this._retryTimer = window.setTimeout(() => {
            this._retryTimer = null;
            resolve();
          }, delays[attempt]);
        });
      }
    }
  };

  private _loadModels = async () => {
    try {
      const resp = await this.props.service.listModels();
      this.setState({
        providers: resp.providers,
        coder: resp.current,
        modelsError: null
      });
    } catch (err) {
      this.setState({
        modelsError: err instanceof Error ? err.message : String(err)
      });
    }
  };

  private _unmounted = false;
  private _retryTimer: number | null = null;

  private _onCoderChanged = (_: IAiCoderService, info: CoderInfo) => {
    this.setState({ coder: info });
  };

  private _onModelSelect = async (
    model: string,
    providerKey: string | null,
    persist: boolean
  ) => {
    try {
      await this.props.service.setCoderModel({
        model,
        providerKey,
        persist
      });
    } catch (err) {
      this.setState({
        modelsError: err instanceof Error ? err.message : String(err)
      });
    }
  };

  private _onCurrentChanged = (_t: any, panel: NotebookPanel | null) => {
    this.setState({ panel, pendingPermissions: [], rev: this.state.rev + 1 });
  };

  private _onAgentEvent = () => {
    this.setState({ rev: this.state.rev + 1 });
  };

  private _onTurnComplete = () => {
    this.setState({ busy: false, rev: this.state.rev + 1 });
  };

  private _onPermission = (
    _s: IAiCoderService,
    args: { panel: NotebookPanel; request: PermissionRequestOut }
  ) => {
    if (args.panel !== this.state.panel) return;
    this.setState({
      pendingPermissions: [...this.state.pendingPermissions, args.request]
    });
  };

  private _decide = async (
    req: PermissionRequestOut,
    decision: 'grant' | 'deny' | 'grant_session'
  ) => {
    const panel = this.state.panel;
    if (!panel) return;
    await this.props.service.decidePermission(panel, req.request_id, decision);
    this.setState({
      pendingPermissions: this.state.pendingPermissions.filter(
        p => p.request_id !== req.request_id
      )
    });
  };

  private _submit = async () => {
    // Block re-entry while a turn is already in flight. Otherwise hitting
    // Enter twice spawns two ``runUserMessage`` calls, the second clobbers
    // ``activeTurn`` and any events streamed for the first turn land in the
    // wrong bucket (or are dropped entirely if the second turn finishes
    // first). Visible symptom: two "You" bubbles and zero assistant
    // bubbles, with the Send button briefly flipping to Stop and back.
    if (this.state.busy) return;
    const text = this.state.input.trim();
    if (!text) return;
    const panel = this.state.panel;
    if (!panel) return;
    const { service } = this.props;
    const refs = parseReferences(text);
    const slash = applySlashCommand(text);
    const cellRefs = refs.cellRefs.map(idx => {
      const src = panel.content.widgets[idx]?.model.sharedModel.getSource() || '';
      return { index: idx, source: src };
    });
    this.setState({ input: '', busy: true });
    try {
      await service.runUserMessage({
        panel,
        text: slash.text,
        cellRefs,
        fileRefs: refs.fileRefs,
        planMode: slash.planMode
      });
    } catch (err) {
      // ``runUserMessage`` rejects when the WebSocket fails to connect or
      // ``sendUserMessage`` errors before the backend can stream anything
      // back. Without this catch the promise rejection is unhandled and
      // ``busy`` stays ``true`` forever -- the Send button is stuck in
      // "Stop" state with no visible error. Surface the failure as an
      // error block in the active turn and release the busy lock.
      const msg = err instanceof Error ? err.message : String(err);
      // eslint-disable-next-line no-console
      console.error('[ai-coder] runUserMessage failed:', err);
      this.setState({ busy: false });
      // Use the service signal so TurnView re-renders the error in place.
      // We don't have a direct handle to the active turn here, but the
      // service knows about it -- we emit a synthetic error event via the
      // public ``agentEvent`` signal. If no active turn exists (race), it
      // simply broadcasts to listeners which is fine.
      (service as unknown as {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        agentEvent: { emit: (a: any) => void };
      }).agentEvent.emit({
        panel,
        event: {
          kind: 'agent_event',
          event_type: 'error',
          error: `send failed: ${msg}`,
          done: true,
          is_error: true
        }
      });
    }
  };

  private _cancel = async () => {
    const panel = this.state.panel;
    if (!panel) return;
    await this.props.service.cancel(panel);
    this.setState({ busy: false });
  };

  private _onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void this._submit();
    }
  };

  render(): JSX.Element {
    const trans = this.props.translator.load('jupyterlab');
    const {
      panel,
      input,
      pendingPermissions,
      busy,
      coder,
      providers,
      modelsError
    } = this.state;
    const turns = panel ? this.props.service.getTurns(panel) : [];
    const visibleTurns = turns.slice(-MAX_RENDERED_TURNS);

    return (
      <div className="jp-AiCoderSidebar">
        <div className="jp-AiCoderSidebar-header">
          <span>
            {trans.__('AI Coder')}
            {panel ? ` · ${panel.context?.path?.split('/').pop() ?? ''}` : ''}
          </span>
          <button
            className="jp-AiCoder-button"
            onClick={() => this.setState({ rev: this.state.rev + 1 })}
            title={trans.__('Refresh')}
          >
            ↻
          </button>
        </div>

        <ModelPicker
          coder={coder}
          providers={providers}
          busy={busy}
          error={modelsError}
          onSelect={this._onModelSelect}
          onReload={this._loadModels}
          translator={this.props.translator}
        />


        <div className="jp-AiCoderSidebar-body">
          {visibleTurns.length === 0 ? (
            <div className="jp-AiTaskPanel-empty">
              {panel
                ? trans.__('Ask me anything about this notebook. Try /plan, /explain, /test, /refactor.')
                : trans.__('Open a notebook to start chatting with AI Coder.')}
            </div>
          ) : (
            visibleTurns.map(turn => (
              <TurnView
                key={turn.id}
                turn={turn}
                translator={this.props.translator}
                rendermime={this.props.rendermime}
                coder={coder}
              />
            ))
          )}

          {pendingPermissions.map(req => (
            <PermBanner
              key={req.request_id}
              req={req}
              onDecide={this._decide}
              translator={this.props.translator}
            />
          ))}
        </div>

        <div className="jp-AiCoderSidebar-footer">
          <div className="jp-AiCoder-composer">
            <div className="jp-AiCoder-composer-refs">
              {Object.entries(SLASH_COMMANDS).map(([cmd, def]) => (
                <span
                  className="jp-AiCoder-chip"
                  key={cmd}
                  onClick={() =>
                    this.setState({
                      input: this.state.input + (this.state.input ? ' ' : '') + `/${cmd} `
                    })
                  }
                  title={def.label}
                >
                  /{cmd}
                </span>
              ))}
            </div>
            <textarea
              className="jp-AiCoder-composer-input"
              placeholder={trans.__(
                'Ask anything. Use @cell-N to reference cells, #path/to/file for files.'
              )}
              value={input}
              onChange={e => this.setState({ input: e.target.value })}
              onKeyDown={this._onKeyDown}
            />
            <div className="jp-AiCoder-composer-toolbar">
              <span style={{ fontSize: 'var(--jp-ui-font-size0)', color: 'var(--jp-ui-font-color2)' }}>
                {trans.__('Shift+Enter for newline · Enter to send')}
              </span>
              <div>
                {busy ? (
                  <button className="jp-AiCoder-button" onClick={this._cancel}>
                    {trans.__('Stop')}
                  </button>
                ) : (
                  <button
                    className="jp-AiCoder-button jp-mod-primary"
                    onClick={this._submit}
                    disabled={!panel}
                  >
                    {trans.__('Send')}
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }
}

function TurnView(props: {
  turn: {
    id: string;
    userText: string;
    events: AgentEventOut[];
    isError: boolean;
    finishedAt: number | null;
  };
  translator: ITranslator;
  rendermime: IRenderMimeRegistry | null;
  coder: CoderInfo | null;
}): JSX.Element {
  const { turn } = props;
  return (
    <div>
      <div className="jp-AiCoder-msg jp-mod-user">
        <div className="jp-AiCoder-msg-role">You</div>
        <div style={{ whiteSpace: 'pre-wrap' }}>{turn.userText}</div>
      </div>
      <AssistantStream
        events={turn.events}
        translator={props.translator}
        rendermime={props.rendermime}
        turnFinished={turn.finishedAt !== null}
        turnIsError={turn.isError}
        coder={props.coder}
      />
    </div>
  );
}

function ThinkingBlock(props: {
  content: string;
  translator: ITranslator;
  rendermime: IRenderMimeRegistry | null;
}): JSX.Element {
  const trans = props.translator.load('jupyterlab');
  const [open, setOpen] = React.useState<boolean>(() =>
    readThinkingDefaultOpen()
  );

  const firstNonEmptyLine =
    props.content.split('\n').find(s => s.trim().length > 0) ?? '';
  const trimmed = firstNonEmptyLine.trim();
  const preview =
    trimmed.length > 80 ? trimmed.slice(0, 80) + '…' : trimmed;

  const tokenCount = React.useMemo(
    () => estimateTokens(props.content),
    [props.content]
  );

  // Use a controlled ``<details>``: ``onToggle`` fires whether the change came
  // from a user click or programmatic. We persist the new state as the new
  // default so the next thinking block (and next session) inherits it.
  const onToggle = (e: React.SyntheticEvent<HTMLDetailsElement>) => {
    const next = (e.currentTarget as HTMLDetailsElement).open;
    if (next !== open) {
      setOpen(next);
      writeThinkingDefaultOpen(next);
    }
  };

  return (
    <details
      className="jp-AiCoder-thinking"
      open={open}
      onToggle={onToggle}
    >
      <summary className="jp-AiCoder-thinking-summary">
        <span className="jp-AiCoder-thinking-icon" aria-hidden="true">
          💭
        </span>
        <span className="jp-AiCoder-thinking-label">
          {trans.__('Reasoning')}
        </span>
        <span
          className="jp-AiCoder-thinking-count"
          title={trans.__('Approximate token count (estimated, not exact)')}
        >
          {/* "~N tokens" rather than "N tokens" so users don't expect bill-grade accuracy */}
          {`~${tokenCount} ${tokenCount === 1 ? 'token' : 'tokens'}`}
        </span>
        {preview ? (
          <span className="jp-AiCoder-thinking-preview" title={preview}>
            {preview}
          </span>
        ) : null}
      </summary>
      <div className="jp-AiCoder-thinking-body">
        <MarkdownView
          content={props.content}
          rendermime={props.rendermime}
        />
      </div>
    </details>
  );
}

function ToolChip(props: { item: Extract<StreamItem, { kind: 'tool' }> }): JSX.Element {
  const { item } = props;
  const cls =
    'jp-AiCoder-toolchip' +
    (item.status === 'pending' ? ' jp-mod-pending' : '') +
    (item.status === 'error' ? ' jp-mod-error' : '');
  const icon =
    item.status === 'error' ? '✗' : item.status === 'done' ? '✓' : '🔧';
  return (
    <span className={cls} title={item.result}>
      {icon} {item.tool_name}
    </span>
  );
}

function AssistantStream(props: {
  events: AgentEventOut[];
  translator: ITranslator;
  rendermime: IRenderMimeRegistry | null;
  turnFinished: boolean;
  turnIsError: boolean;
  coder: CoderInfo | null;
}): JSX.Element {
  const trans = props.translator.load('jupyterlab');
  const items = reduceStreamEvents(props.events);
  // Diagnostic: if a turn finished but produced ZERO renderable items, show
  // a hint so the user sees that the agent loop terminated rather than
  // assuming the request is still flying. Common causes: provider returned
  // only a ``response`` terminator with empty content, a serializer error
  // ate all events, or the LLM emitted reasoning_content only.
  if (props.turnFinished && items.length === 0) {
    // Surface the active model/provider so the user knows *which* coder
    // produced no output — otherwise this looks like a generic UI bug.
    const c = props.coder;
    const modelTag =
      c && (c.model || c.provider_key)
        ? `(${c.provider_key ?? '?'} · ${c.model ?? '?'})`
        : '';
    // Aggregate usage from any ``usage`` events that did arrive, so we can
    // tell e.g. ``input=8200 output=0`` (model spent it all on reasoning and
    // hit max_tokens) apart from ``input=0 output=0`` (request never made
    // it to the model).
    let inTok = 0;
    let outTok = 0;
    for (const ev of props.events) {
      if (ev.event_type === 'usage' && ev.usage) {
        inTok = ev.usage.input_tokens || 0;
        outTok = ev.usage.output_tokens || 0;
      }
    }
    const usageTag =
      inTok > 0 || outTok > 0
        ? ` · usage in=${inTok} out=${outTok}`
        : '';

    items.push({
      kind: 'error',
      message: props.turnIsError
        ? trans.__(
            'Turn ended with an error and no content %1%2. Check the Jupyter server logs.',
            modelTag,
            usageTag
          )
        : trans.__(
            'Agent produced no visible output %1%2. The model finished cleanly but emitted no content or reasoning — likely an invalid model/base_url combination, or max_tokens spent entirely inside silent reasoning. Try a different model from the picker above and check the Jupyter server logs.',
            modelTag,
            usageTag
          )
    });
  }
  return (
    <>
      {items.map((item, i) => {
        switch (item.kind) {
          case 'thinking':
            return (
              <ThinkingBlock
                key={`th-${i}`}
                content={item.content}
                translator={props.translator}
                rendermime={props.rendermime}
              />
            );
          case 'text':
            return (
              <div key={`t-${i}`} className="jp-AiCoder-msg">
                <div className="jp-AiCoder-msg-role">AI</div>
                <MarkdownView
                  content={item.content}
                  rendermime={props.rendermime}
                />
              </div>
            );
          case 'tool':
            return <ToolChip key={`tool-${i}`} item={item} />;
          case 'error':
            return (
              <div
                key={`err-${i}`}
                className="jp-AiCoder-msg"
                style={{ color: 'var(--jp-error-color0)' }}
              >
                {item.message}
              </div>
            );
          default:
            return null;
        }
      })}
    </>
  );
}

function PermBanner(props: {
  req: PermissionRequestOut;
  onDecide: (
    req: PermissionRequestOut,
    decision: 'grant' | 'deny' | 'grant_session'
  ) => void;
  translator: ITranslator;
}): JSX.Element {
  const trans = props.translator.load('jupyterlab');
  return (
    <div className="jp-AiPermBanner">
      <div>
        <strong>{trans.__('Permission needed')}</strong> · {props.req.tool_name}
      </div>
      <div style={{ fontSize: 'var(--jp-ui-font-size0)' }}>{props.req.description}</div>
      {props.req.path ? (
        <div style={{ fontSize: 'var(--jp-ui-font-size0)' }}>{props.req.path}</div>
      ) : null}
      <div className="jp-AiPermBanner-actions">
        <button
          className="jp-AiCoder-button"
          onClick={() => props.onDecide(props.req, 'deny')}
        >
          {trans.__('Deny')}
        </button>
        <button
          className="jp-AiCoder-button"
          onClick={() => props.onDecide(props.req, 'grant')}
        >
          {trans.__('Allow once')}
        </button>
        <button
          className="jp-AiCoder-button jp-mod-primary"
          onClick={() => props.onDecide(props.req, 'grant_session')}
        >
          {trans.__('Allow session')}
        </button>
      </div>
    </div>
  );
}

export class ChatPanelWidget extends ReactWidget {
  constructor(opts: {
    service: IAiCoderService;
    tracker: INotebookTracker;
    translator?: ITranslator;
    rendermime?: IRenderMimeRegistry | null;
  }) {
    super();
    this._service = opts.service;
    this._tracker = opts.tracker;
    this._translator = opts.translator ?? nullTranslator;
    this._rendermime = opts.rendermime ?? null;
    this.addClass('jp-AiCoderSidebar');
    this.id = 'jp-ai-coder-sidebar';
    this.title.closable = true;
  }

  protected render(): JSX.Element {
    return (
      <ChatPanelComponent
        service={this._service}
        tracker={this._tracker}
        translator={this._translator}
        rendermime={this._rendermime}
      />
    );
  }

  private _service: IAiCoderService;
  private _tracker: INotebookTracker;
  private _translator: ITranslator;
  private _rendermime: IRenderMimeRegistry | null;
}
