// Copyright (c) Jupyter Studio AI.
// Distributed under the terms of the Modified BSD License.
//
// Implements the reverse-RPC handlers (listCells/readCell/editCell/runCell ...)
// against a JupyterLab NotebookPanel. All cell-modifying operations go through
// ``sharedModel.transact`` so they cooperate with yjs / collaborative editing.

import { Cell, CodeCell, ICellModel } from '@jupyterlab/cells';
import { NotebookActions, NotebookPanel } from '@jupyterlab/notebook';
import { AiTransport, RpcHandler } from './transport';

interface CellSummary {
  index: number;
  cell_type: 'code' | 'markdown' | 'raw';
  source_preview: string;
  execution_count: number | null;
  has_output: boolean;
}

/**
 * Build a snapshot of all cells, used both for ``notebook_state`` push and
 * the ``listCells`` reverse RPC.
 */
export function snapshotCells(panel: NotebookPanel): CellSummary[] {
  const cells = panel.content.widgets;
  return cells.map((cell, index) => _summarize(cell, index));
}

function _summarize(cell: Cell<ICellModel>, index: number): CellSummary {
  const model = cell.model;
  const src = model.sharedModel.getSource();
  const preview = src.length > 200 ? src.slice(0, 200) + '\u2026' : src;
  return {
    index,
    cell_type: model.type as 'code' | 'markdown' | 'raw',
    source_preview: preview,
    execution_count: model.type === 'code' ? (model as any).executionCount ?? null : null,
    has_output: cell instanceof CodeCell && (cell.model as any).outputs?.length > 0
  };
}

function _getActiveCellIndex(panel: NotebookPanel): number {
  return panel.content.activeCellIndex ?? 0;
}

function _outputsAsText(cell: Cell<ICellModel>): {
  text: string;
  has_error: boolean;
  execution_count: number | null;
} {
  if (!(cell instanceof CodeCell)) {
    return { text: '', has_error: false, execution_count: null };
  }
  const outputs = (cell.model as any).outputs;
  const lines: string[] = [];
  let hasError = false;
  for (let i = 0; i < outputs.length; i++) {
    const out = outputs.get(i);
    const data = out.toJSON();
    switch (data.output_type) {
      case 'stream':
        lines.push(String(data.text ?? ''));
        if (data.name === 'stderr') {
          hasError = hasError || true;
        }
        break;
      case 'error':
        hasError = true;
        lines.push(`${data.ename}: ${data.evalue}`);
        if (Array.isArray(data.traceback)) {
          lines.push(data.traceback.join('\n'));
        }
        break;
      case 'execute_result':
      case 'display_data': {
        const d = (data as any).data || {};
        if (typeof d['text/plain'] === 'string') {
          lines.push(d['text/plain']);
        } else if (Array.isArray(d['text/plain'])) {
          lines.push(d['text/plain'].join(''));
        }
        break;
      }
      default:
        break;
    }
  }
  return {
    text: lines.join('\n'),
    has_error: hasError,
    execution_count: (cell.model as any).executionCount ?? null
  };
}

/**
 * Bind reverse-RPC handlers on the transport for a specific notebook.
 *
 * The transport is shared per-session; we rebind handlers when the active
 * notebook changes so every RPC operates on the panel currently in focus.
 */
export function bindNotebookOps(
  transport: AiTransport,
  getPanel: () => NotebookPanel | null
): void {
  const need = (): NotebookPanel => {
    const p = getPanel();
    if (p === null) {
      throw new Error('no active notebook panel');
    }
    return p;
  };

  const handlers: Record<string, RpcHandler> = {
    async listCells() {
      return snapshotCells(need());
    },

    async readCell(params) {
      const panel = need();
      const idx = Number(params.index ?? 0);
      const cell = panel.content.widgets[idx];
      if (!cell) {
        throw new Error(`cell ${idx} out of range`);
      }
      return {
        index: idx,
        cell_type: cell.model.type,
        source: cell.model.sharedModel.getSource()
      };
    },

    async readCellOutput(params) {
      const panel = need();
      const idx = Number(params.index ?? 0);
      const cell = panel.content.widgets[idx];
      if (!cell) {
        throw new Error(`cell ${idx} out of range`);
      }
      return _outputsAsText(cell);
    },

    async editCell(params) {
      const panel = need();
      const idx = Number(params.index ?? 0);
      const source = String(params.source ?? '');
      const cell = panel.content.widgets[idx];
      if (!cell) {
        throw new Error(`cell ${idx} out of range`);
      }
      cell.model.sharedModel.transact(() => {
        cell.model.sharedModel.setSource(source);
      });
      return { index: idx, length: source.length };
    },

    async insertCell(params) {
      const panel = need();
      const idx = Math.max(0, Number(params.index ?? 0));
      const source = String(params.source ?? '');
      const cellType = (params.cell_type as string) ?? 'code';
      const model = panel.content.model;
      if (!model) {
        throw new Error('notebook model not ready');
      }
      const sharedModel = model.sharedModel;
      const safeIdx = Math.min(idx, sharedModel.cells.length);
      sharedModel.transact(() => {
        sharedModel.insertCell(safeIdx, {
          cell_type: cellType as any,
          source
        });
      });
      panel.content.activeCellIndex = safeIdx;
      return { index: safeIdx };
    },

    async deleteCell(params) {
      const panel = need();
      const idx = Number(params.index ?? 0);
      const model = panel.content.model;
      if (!model) {
        throw new Error('notebook model not ready');
      }
      model.sharedModel.transact(() => {
        model.sharedModel.deleteCell(idx);
      });
      return { index: idx };
    },

    async runCell(params) {
      const panel = need();
      const idx = Number(params.index ?? 0);
      const cell = panel.content.widgets[idx];
      if (!cell) {
        throw new Error(`cell ${idx} out of range`);
      }
      panel.content.activeCellIndex = idx;
      const session = panel.sessionContext;
      const success = await NotebookActions.run(panel.content, session);
      const result = _outputsAsText(cell);
      return { ...result, success };
    },

    async setCellMetadata(params) {
      const panel = need();
      const idx = Number(params.index ?? 0);
      const metadata = (params.metadata as Record<string, unknown>) ?? {};
      const cell = panel.content.widgets[idx];
      if (!cell) {
        throw new Error(`cell ${idx} out of range`);
      }
      cell.model.sharedModel.transact(() => {
        for (const [k, v] of Object.entries(metadata)) {
          cell.model.setMetadata(k, v as any);
        }
      });
      return { index: idx, keys: Object.keys(metadata) };
    }
  };

  for (const [name, fn] of Object.entries(handlers)) {
    transport.registerRpc(name, fn);
  }
}

/**
 * Build a notebook-state snapshot frame.
 */
export function buildNotebookStateFrame(panel: NotebookPanel): {
  cells: CellSummary[];
  activeCellIndex: number;
  notebookPath: string | null;
} {
  return {
    cells: snapshotCells(panel),
    activeCellIndex: _getActiveCellIndex(panel),
    notebookPath: panel.context?.path ?? null
  };
}
