// Copyright (c) Jupyter Studio AI.
//
// Listen for failed cell executions and offer a one-click `Fix with AI` action
// surfaced as a transient command palette entry + cell footer highlight.

import { JupyterFrontEnd, JupyterFrontEndPlugin } from '@jupyterlab/application';
import { CodeCell } from '@jupyterlab/cells';
import {
  INotebookTracker,
  NotebookActions,
  NotebookPanel
} from '@jupyterlab/notebook';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';

import { FIX_LAST_ERROR_COMMAND } from './inlineEdit';

const HIGHLIGHT_CLASS = 'jp-mod-ai-fix-pending';

export const errorFixPlugin: JupyterFrontEndPlugin<void> = {
  id: '@jupyterlab/ai-coder-extension:error-fix',
  description: 'Surface a Fix-with-AI affordance on failed cell executions.',
  autoStart: true,
  requires: [INotebookTracker],
  optional: [ITranslator],
  activate: (
    app: JupyterFrontEnd,
    tracker: INotebookTracker,
    translator: ITranslator | null
  ): void => {
    const trans = (translator ?? nullTranslator).load('jupyterlab');

    NotebookActions.executed.connect((_sender, args) => {
      if (!args || args.success !== false) return;
      const cell = args.cell;
      if (!(cell instanceof CodeCell)) return;
      cell.node.classList.add(HIGHLIGHT_CLASS);
      const footerBtn = cell.node.querySelector(
        '.jp-AiCellFooter-button.jp-mod-danger'
      ) as HTMLButtonElement | null;
      if (footerBtn) {
        footerBtn.style.display = '';
        footerBtn.animate(
          [
            { boxShadow: '0 0 0 0 var(--jp-error-color1)' },
            { boxShadow: '0 0 0 4px transparent' }
          ],
          { duration: 800, iterations: 2 }
        );
      }
    });

    // Also expose a global command equivalent on the active cell.
    app.commands.addCommand('ai-coder:fix-active-error', {
      label: trans.__('AI Coder: Fix last execution error'),
      isEnabled: () => {
        const panel: NotebookPanel | null = tracker.currentWidget;
        return !!panel && panel.content.activeCell instanceof CodeCell;
      },
      execute: () => app.commands.execute(FIX_LAST_ERROR_COMMAND, {})
    });
  }
};
