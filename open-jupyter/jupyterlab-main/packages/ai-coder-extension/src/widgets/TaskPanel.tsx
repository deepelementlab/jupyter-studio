// Copyright (c) Jupyter Studio AI.

import {
  AgentEventOut,
  IAiCoderService
} from '@jupyterlab/ai-coder';
import { INotebookTracker, NotebookPanel } from '@jupyterlab/notebook';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';
import { ReactWidget } from '@jupyterlab/ui-components';
import * as React from 'react';

interface TodoItem {
  id?: string;
  content: string;
  status: 'pending' | 'in_progress' | 'completed' | 'cancelled';
}

function parseTodoArgs(args: unknown): TodoItem[] {
  // clawcode's TodoWrite tool input is `{ todos: [...] }` or
  // `{ todos: { todos: [...] } }` depending on provider variations.
  if (!args || typeof args !== 'object') return [];
  const a = args as Record<string, unknown>;
  const direct = a.todos;
  if (Array.isArray(direct)) return direct as TodoItem[];
  if (direct && typeof direct === 'object') {
    const nested = (direct as Record<string, unknown>).todos;
    if (Array.isArray(nested)) return nested as TodoItem[];
  }
  return [];
}

interface ToolCall {
  ts: number;
  name: string;
  status: 'pending' | 'done' | 'error';
  result?: string;
}

interface Aggregate {
  todos: TodoItem[];
  tools: ToolCall[];
}

function reduceEvents(events: AgentEventOut[]): Aggregate {
  let todos: TodoItem[] = [];
  const tools: ToolCall[] = [];
  for (const ev of events) {
    if (ev.event_type === 'tool_use' && ev.tool_name) {
      tools.push({
        ts: Date.now(),
        name: ev.tool_name,
        status: 'pending'
      });
      if (ev.tool_name === 'TodoWrite') {
        const next = parseTodoArgs(ev.tool_input);
        if (next.length) todos = next;
      }
    } else if (ev.event_type === 'tool_result' && ev.tool_name) {
      // mark the latest matching pending tool as done
      for (let i = tools.length - 1; i >= 0; i--) {
        if (tools[i].name === ev.tool_name && tools[i].status === 'pending') {
          tools[i].status = ev.is_error ? 'error' : 'done';
          tools[i].result = ev.tool_result?.slice(0, 200);
          break;
        }
      }
    }
  }
  return { todos, tools };
}

interface TaskPanelProps {
  service: IAiCoderService;
  tracker: INotebookTracker;
  translator: ITranslator;
}
interface TaskPanelState {
  rev: number;
  panel: NotebookPanel | null;
}

class TaskPanelComponent extends React.Component<TaskPanelProps, TaskPanelState> {
  state: TaskPanelState = {
    rev: 0,
    panel: this.props.tracker.currentWidget
  };

  componentDidMount(): void {
    this.props.service.agentEvent.connect(this._bump, this);
    this.props.tracker.currentChanged.connect(this._onTracker, this);
  }
  componentWillUnmount(): void {
    this.props.service.agentEvent.disconnect(this._bump, this);
    this.props.tracker.currentChanged.disconnect(this._onTracker, this);
  }
  private _bump = () => this.setState({ rev: this.state.rev + 1 });
  private _onTracker = (_t: any, panel: NotebookPanel | null) =>
    this.setState({ panel, rev: this.state.rev + 1 });

  render(): JSX.Element {
    const trans = this.props.translator.load('jupyterlab');
    const { panel } = this.state;
    const turns = panel ? this.props.service.getTurns(panel) : [];
    const allEvents: AgentEventOut[] = [];
    for (const t of turns) {
      for (const e of t.events) {
        allEvents.push(e);
      }
    }
    const { todos, tools } = reduceEvents(allEvents);

    return (
      <div className="jp-AiCoderSidebar">
        <div className="jp-AiCoderSidebar-header">
          <span>{trans.__('AI Tasks')}</span>
        </div>
        <div className="jp-AiCoderSidebar-body">
          <div className="jp-AiTaskPanel-section">
            <div className="jp-AiTaskPanel-title">{trans.__('Plan')}</div>
            {todos.length === 0 ? (
              <div className="jp-AiTaskPanel-empty">
                {trans.__('No agent plan yet. Ask /plan ... to start.')}
              </div>
            ) : (
              todos.map((todo, i) => (
                <div
                  key={i}
                  className={
                    'jp-AiTaskPanel-item' +
                    (todo.status === 'completed' ? ' jp-mod-done' : '')
                  }
                >
                  <span>
                    {todo.status === 'completed'
                      ? '\u2713'
                      : todo.status === 'in_progress'
                      ? '\u25D0'
                      : todo.status === 'cancelled'
                      ? '\u2715'
                      : '\u25CB'}
                  </span>
                  <span>{todo.content}</span>
                </div>
              ))
            )}
          </div>

          <div className="jp-AiTaskPanel-section">
            <div className="jp-AiTaskPanel-title">{trans.__('Tool calls')}</div>
            {tools.length === 0 ? (
              <div className="jp-AiTaskPanel-empty">
                {trans.__('No tools have been called yet.')}
              </div>
            ) : (
              tools.slice(-25).map((tc, i) => (
                <div key={i} className="jp-AiTaskPanel-item">
                  <span>
                    {tc.status === 'done'
                      ? '\u2713'
                      : tc.status === 'error'
                      ? '\u2717'
                      : '\u25CB'}
                  </span>
                  <span>{tc.name}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    );
  }
}

export class TaskPanelWidget extends ReactWidget {
  constructor(opts: {
    service: IAiCoderService;
    tracker: INotebookTracker;
    translator?: ITranslator;
  }) {
    super();
    this._service = opts.service;
    this._tracker = opts.tracker;
    this._translator = opts.translator ?? nullTranslator;
    this.addClass('jp-AiCoderSidebar');
    this.id = 'jp-ai-coder-task-panel';
    this.title.closable = true;
  }
  protected render(): JSX.Element {
    return (
      <TaskPanelComponent
        service={this._service}
        tracker={this._tracker}
        translator={this._translator}
      />
    );
  }
  private _service: IAiCoderService;
  private _tracker: INotebookTracker;
  private _translator: ITranslator;
}
