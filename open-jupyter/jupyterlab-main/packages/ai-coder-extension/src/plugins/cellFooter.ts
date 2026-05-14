// Copyright (c) Jupyter Studio AI.
//
// Attach a hover-visible AI mini-toolbar inside each code cell's default
// CellFooter (.jp-CellFooter). This avoids overriding the NotebookPanel
// IContentFactory token (which would conflict with existing customizations
// and risks duplicate-token errors at app start) - we just place a child
// node inside the cell's existing footer element.

import { JupyterFrontEnd, JupyterFrontEndPlugin } from '@jupyterlab/application';
import { Cell, CodeCell } from '@jupyterlab/cells';
import { INotebookTracker, Notebook, NotebookPanel } from '@jupyterlab/notebook';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';
import { IDisposable } from '@lumino/disposable';

import { cellErrorText } from '../utils';
import { INLINE_EDIT_COMMAND, FIX_LAST_ERROR_COMMAND } from './inlineEdit';

const FOOTER_CLASS = 'jp-AiCellFooter';

export const cellFooterPlugin: JupyterFrontEndPlugin<void> = {
  id: '@jupyterlab/ai-coder-extension:cell-footer',
  description: 'Render an AI mini-toolbar inside the standard cell footer.',
  autoStart: true,
  requires: [INotebookTracker],
  optional: [ITranslator],
  activate: (
    app: JupyterFrontEnd,
    tracker: INotebookTracker,
    translator: ITranslator | null
  ): void => {
    const trans = (translator ?? nullTranslator).load('jupyterlab');

    const setupCell = (cell: Cell): IDisposable | null => {
      if (!(cell instanceof CodeCell)) return null;
      const footerNode = cell.node.querySelector('.jp-CellFooter') as HTMLElement | null;
      if (!footerNode) return null;
      if (footerNode.querySelector(`.${FOOTER_CLASS}`)) return null;
      const bar = document.createElement('div');
      bar.className = FOOTER_CLASS;

      const editBtn = mkBtn(
        '\u2728 ' + trans.__('Edit'),
        trans.__('Edit this cell with AI (\u2318K)'),
        () =>
          app.commands.execute(INLINE_EDIT_COMMAND, {
            instruction: ''
          })
      );
      bar.appendChild(editBtn);

      const explainBtn = mkBtn(
        '\ud83d\udcac ' + trans.__('Explain'),
        trans.__('Ask the AI to explain this cell'),
        () =>
          app.commands.execute(INLINE_EDIT_COMMAND, {
            instruction: trans.__(
              'Explain the cell above in plain language. Reply by inserting a markdown comment block at the top of the cell, do not rewrite the executable code.'
            )
          })
      );
      bar.appendChild(explainBtn);

      const fixBtn = mkBtn(
        '\ud83d\udc1b ' + trans.__('Fix'),
        trans.__('Fix the last error in this cell using AI'),
        () => app.commands.execute(FIX_LAST_ERROR_COMMAND, {})
      );
      fixBtn.classList.add('jp-mod-danger');
      bar.appendChild(fixBtn);

      const updateVisibility = () => {
        const err = cellErrorText(cell);
        fixBtn.style.display = err ? '' : 'none';
      };
      updateVisibility();
      (cell.model as any).outputs?.changed?.connect?.(updateVisibility);
      const dispose = () => {
        try {
          (cell.model as any).outputs?.changed?.disconnect?.(updateVisibility);
        } catch {
          /* noop */
        }
        try {
          bar.remove();
        } catch {
          /* noop */
        }
      };
      footerNode.appendChild(bar);
      const disposable: IDisposable = {
        dispose,
        isDisposed: false
      };
      return disposable;
    };

    const setupNotebook = (panel: NotebookPanel) => {
      const notebook: Notebook = panel.content;
      const disposers: IDisposable[] = [];
      const attachAll = () => {
        notebook.widgets.forEach(cell => {
          const d = setupCell(cell);
          if (d) disposers.push(d);
        });
      };
      attachAll();
      const onCellAdded = () => attachAll();
      notebook.modelContentChanged.connect(onCellAdded);
      panel.disposed.connect(() => {
        notebook.modelContentChanged.disconnect(onCellAdded);
        disposers.forEach(d => d.dispose());
      });
    };

    tracker.forEach(setupNotebook);
    tracker.widgetAdded.connect((_t, panel) => {
      panel.revealed.then(() => setupNotebook(panel)).catch(() => undefined);
    });
  }
};

function mkBtn(label: string, title: string, onClick: () => void): HTMLButtonElement {
  const b = document.createElement('button');
  b.className = 'jp-AiCellFooter-button';
  b.textContent = label;
  b.title = title;
  b.onclick = ev => {
    ev.preventDefault();
    ev.stopPropagation();
    onClick();
  };
  return b;
}
